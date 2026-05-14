"""Database migration: create tables and record schema version.

Schema history:
  v1 — tasks table without owner_user_id
  v2 — tasks table with owner_user_id and updated_by_user_id (current)

Sessions and OAuth state are stored in Redis; no database tables are
needed for them.
"""

from backend.database.db import get_connection
from backend.database.models import ALL_DDL, SCHEMA_VERSION


def _get_current_schema_version(cursor) -> int:
    """Return the highest recorded schema version, or 0 if none."""
    cursor.execute("SHOW TABLES LIKE 'schema_version'")
    if cursor.fetchone() is None:
        return 0
    cursor.execute("SELECT COALESCE(MAX(version), 0) AS v FROM schema_version")
    row = cursor.fetchone()
    return int(row["v"]) if row else 0


def _column_exists(cursor, table: str, column: str) -> bool:
    """Check if a column exists in a table."""
    cursor.execute(
        "SELECT 1 FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s",
        (table, column),
    )
    return cursor.fetchone() is not None


def _index_exists(cursor, table: str, index_name: str) -> bool:
    """Check if an index exists on a table."""
    cursor.execute(
        "SELECT 1 FROM information_schema.STATISTICS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND INDEX_NAME = %s",
        (table, index_name),
    )
    return cursor.fetchone() is not None


def _constraint_exists(cursor, table: str, constraint_name: str) -> bool:
    """Check if a foreign key constraint exists on a table."""
    cursor.execute(
        "SELECT 1 FROM information_schema.TABLE_CONSTRAINTS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s "
        "AND CONSTRAINT_NAME = %s AND CONSTRAINT_TYPE = 'FOREIGN KEY'",
        (table, constraint_name),
    )
    return cursor.fetchone() is not None


def _apply_v2_migration(cursor) -> None:
    """Apply v1→v2 migration: add auth columns to tasks table.

    Uses information_schema checks before each ALTER TABLE to ensure
    idempotency (MySQL does not support ADD COLUMN IF NOT EXISTS).
    """
    # Add owner_user_id column
    if not _column_exists(cursor, "tasks", "owner_user_id"):
        cursor.execute(
            "ALTER TABLE tasks ADD COLUMN "
            "owner_user_id INT UNSIGNED NOT NULL AFTER id"
        )

    # Add updated_by_user_id column
    if not _column_exists(cursor, "tasks", "updated_by_user_id"):
        cursor.execute(
            "ALTER TABLE tasks ADD COLUMN "
            "updated_by_user_id INT UNSIGNED NULL AFTER status"
        )

    # Add foreign key: owner_user_id → users(id)
    if not _constraint_exists(cursor, "tasks", "fk_tasks_owner"):
        cursor.execute(
            "ALTER TABLE tasks ADD CONSTRAINT fk_tasks_owner "
            "FOREIGN KEY (owner_user_id) REFERENCES users(id) ON DELETE RESTRICT"
        )

    # Add foreign key: updated_by_user_id → users(id)
    if not _constraint_exists(cursor, "tasks", "fk_tasks_updated_by"):
        cursor.execute(
            "ALTER TABLE tasks ADD CONSTRAINT fk_tasks_updated_by "
            "FOREIGN KEY (updated_by_user_id) REFERENCES users(id) ON DELETE SET NULL"
        )

    # Add composite index for owner-scoped listing
    if not _index_exists(cursor, "tasks", "idx_tasks_owner_list"):
        cursor.execute(
            "ALTER TABLE tasks ADD INDEX idx_tasks_owner_list "
            "(owner_user_id, status, created_at DESC)"
        )


def run_migrations() -> None:
    """Execute DDL to ensure schema exists (idempotent via IF NOT EXISTS).

    On a fresh database (version 0), all DDL is applied including the full
    tasks table definition with owner_user_id.

    When upgrading from schema version 1, ALTER TABLE statements add
    owner_user_id / updated_by_user_id to the existing tasks table.
    Existing v1 task data must be deleted beforehand since owner_user_id
    is NOT NULL and this is a pre-release app (no real data to preserve).
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        current_version = _get_current_schema_version(cursor)

        if current_version < SCHEMA_VERSION:
            # Apply all CREATE TABLE IF NOT EXISTS DDL
            for ddl in ALL_DDL:
                cursor.execute(ddl)

            # When upgrading from v1, apply ALTER TABLE changes to add
            # owner_user_id / updated_by_user_id to the existing tasks table.
            if current_version == 1:
                _apply_v2_migration(cursor)

            # Ensure a system user exists (id=1) so that owner_user_id
            # foreign key is satisfied for backward-compatible code paths.
            cursor.execute(
                "INSERT IGNORE INTO users (id, external_id, display_name) "
                "VALUES (1, '__system__', 'System')"
            )

            # Record schema version (INSERT IGNORE for idempotency)
            cursor.execute(
                "INSERT IGNORE INTO schema_version (version) VALUES (%s)",
                (SCHEMA_VERSION,),
            )

            conn.commit()
    finally:
        cursor.close()
        conn.close()
