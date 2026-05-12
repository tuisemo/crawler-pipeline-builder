"""Tests for database migration (v1 → v2 schema upgrade).

Validates that run_migrations() correctly:
- Creates users and sessions tables
- Adds owner_user_id and updated_by_user_id to tasks
- Records schema version 2
- Is idempotent (running twice produces the same result)
- Truncates existing task data on v1→v2 upgrade
"""

from __future__ import annotations

import pymysql
import pytest
from pymysql.cursors import DictCursor

from backend.core.settings import get_settings


def _get_conn() -> pymysql.Connection:
    """Get a direct MySQL connection using project settings."""
    s = get_settings()
    return pymysql.connect(
        host=s.db_host,
        port=int(s.db_port),
        user=s.db_user,
        password=s.db_password,
        database=s.db_name,
        charset="utf8mb4",
        collation="utf8mb4_unicode_ci",
        cursorclass=DictCursor,
        autocommit=False,
    )


# ── Helpers ──────────────────────────────────────────────────────────────


def _table_exists(cursor, name: str) -> bool:
    cursor.execute("SHOW TABLES LIKE %s", (name,))
    return cursor.fetchone() is not None


def _column_names(cursor, table: str) -> set[str]:
    cursor.execute(f"DESCRIBE {table}")
    return {row["Field"] for row in cursor.fetchall()}


def _index_names(cursor, table: str) -> set[str]:
    cursor.execute(f"SHOW INDEX FROM {table}")
    return {row["Key_name"] for row in cursor.fetchall()}


def _constraint_names(cursor, table: str) -> set[str]:
    cursor.execute(
        """
        SELECT CONSTRAINT_NAME
        FROM information_schema.TABLE_CONSTRAINTS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
          AND CONSTRAINT_TYPE = 'FOREIGN KEY'
        """,
        (table,),
    )
    return {row["CONSTRAINT_NAME"] for row in cursor.fetchall()}


# ── Test: Fresh install creates all tables ───────────────────────────────


class TestFreshInstall:
    """Verify that run_migrations() on a fresh database creates all tables."""

    def test_users_table_created(self):
        """users table exists after run_migrations()."""
        from backend.database.migrations import run_migrations

        run_migrations()
        conn = _get_conn()
        try:
            cur = conn.cursor()
            assert _table_exists(cur, "users"), "users table should exist"
        finally:
            conn.close()

    def test_sessions_table_created(self):
        """sessions table exists after run_migrations()."""
        from backend.database.migrations import run_migrations

        run_migrations()
        conn = _get_conn()
        try:
            cur = conn.cursor()
            assert _table_exists(cur, "sessions"), "sessions table should exist"
        finally:
            conn.close()

    def test_tasks_table_has_owner_columns(self):
        """tasks table has owner_user_id and updated_by_user_id columns."""
        from backend.database.migrations import run_migrations

        run_migrations()
        conn = _get_conn()
        try:
            cur = conn.cursor()
            cols = _column_names(cur, "tasks")
            assert "owner_user_id" in cols, "tasks should have owner_user_id"
            assert "updated_by_user_id" in cols, "tasks should have updated_by_user_id"
        finally:
            conn.close()

    def test_schema_version_is_2(self):
        """schema_version table records version 2 after migration."""
        from backend.database.migrations import run_migrations

        run_migrations()
        conn = _get_conn()
        try:
            cur = conn.cursor()
            cur.execute("SELECT version FROM schema_version ORDER BY version")
            versions = [row["version"] for row in cur.fetchall()]
            assert 2 in versions, f"Expected version 2 in schema_version, got {versions}"
        finally:
            conn.close()

    def test_owner_user_id_is_not_null(self):
        """owner_user_id column has NOT NULL constraint."""
        from backend.database.migrations import run_migrations

        run_migrations()
        conn = _get_conn()
        try:
            cur = conn.cursor()
            cur.execute("DESCRIBE tasks")
            rows = cur.fetchall()
            owner_col = next(r for r in rows if r["Field"] == "owner_user_id")
            assert owner_col["Null"] == "NO", "owner_user_id should be NOT NULL"
        finally:
            conn.close()

    def test_updated_by_user_id_is_nullable(self):
        """updated_by_user_id column allows NULL."""
        from backend.database.migrations import run_migrations

        run_migrations()
        conn = _get_conn()
        try:
            cur = conn.cursor()
            cur.execute("DESCRIBE tasks")
            rows = cur.fetchall()
            updated_col = next(r for r in rows if r["Field"] == "updated_by_user_id")
            assert updated_col["Null"] == "YES", "updated_by_user_id should allow NULL"
        finally:
            conn.close()

    def test_tasks_owner_list_index_exists(self):
        """idx_tasks_owner_list composite index exists on tasks."""
        from backend.database.migrations import run_migrations

        run_migrations()
        conn = _get_conn()
        try:
            cur = conn.cursor()
            indexes = _index_names(cur, "tasks")
            assert "idx_tasks_owner_list" in indexes, (
                f"idx_tasks_owner_list should exist, found: {indexes}"
            )
        finally:
            conn.close()

    def test_users_external_id_is_unique(self):
        """users table has UNIQUE constraint on external_id."""
        from backend.database.migrations import run_migrations

        run_migrations()
        conn = _get_conn()
        try:
            cur = conn.cursor()
            cur.execute("SHOW INDEX FROM users WHERE Column_name = 'external_id'")
            rows = cur.fetchall()
            assert any(r["Non_unique"] == 0 for r in rows), (
                "external_id should have a UNIQUE index"
            )
        finally:
            conn.close()

    def test_sessions_token_hash_is_unique(self):
        """sessions table has UNIQUE constraint on token_hash."""
        from backend.database.migrations import run_migrations

        run_migrations()
        conn = _get_conn()
        try:
            cur = conn.cursor()
            cur.execute("SHOW INDEX FROM sessions WHERE Column_name = 'token_hash'")
            rows = cur.fetchall()
            assert any(r["Non_unique"] == 0 for r in rows), (
                "token_hash should have a UNIQUE index"
            )
        finally:
            conn.close()

    def test_sessions_expires_at_index_exists(self):
        """sessions table has index on expires_at for cleanup queries."""
        from backend.database.migrations import run_migrations

        run_migrations()
        conn = _get_conn()
        try:
            cur = conn.cursor()
            indexes = _index_names(cur, "sessions")
            assert "idx_sessions_expires" in indexes, (
                f"idx_sessions_expires should exist, found: {indexes}"
            )
        finally:
            conn.close()

    def test_sessions_user_fk_exists(self):
        """sessions table has foreign key to users(id)."""
        from backend.database.migrations import run_migrations

        run_migrations()
        conn = _get_conn()
        try:
            cur = conn.cursor()
            constraints = _constraint_names(cur, "sessions")
            assert "fk_sessions_user_id" in constraints, (
                f"fk_sessions_user_id should exist, found: {constraints}"
            )
        finally:
            conn.close()

    def test_tasks_owner_fk_exists(self):
        """tasks table has foreign key from owner_user_id to users(id)."""
        from backend.database.migrations import run_migrations

        run_migrations()
        conn = _get_conn()
        try:
            cur = conn.cursor()
            constraints = _constraint_names(cur, "tasks")
            assert "fk_tasks_owner" in constraints, (
                f"fk_tasks_owner should exist, found: {constraints}"
            )
        finally:
            conn.close()


# ── Test: Idempotency ───────────────────────────────────────────────────


class TestIdempotency:
    """Verify that running run_migrations() twice produces the same result."""

    def test_running_twice_does_not_error(self):
        """run_migrations() can be called multiple times without error."""
        from backend.database.migrations import run_migrations

        run_migrations()
        run_migrations()  # Should not raise

    def test_schema_version_unchanged_after_second_run(self):
        """Schema version remains 2 after running migration twice."""
        from backend.database.migrations import run_migrations

        run_migrations()
        run_migrations()

        conn = _get_conn()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) AS cnt FROM schema_version WHERE version = 2")
            count = cur.fetchone()["cnt"]
            assert count == 1, f"Expected exactly 1 row for version 2, got {count}"
        finally:
            conn.close()

    def test_tables_unchanged_after_second_run(self):
        """All tables still exist with correct columns after second migration."""
        from backend.database.migrations import run_migrations

        run_migrations()
        run_migrations()

        conn = _get_conn()
        try:
            cur = conn.cursor()
            for table in ("users", "sessions", "tasks", "task_assets", "schema_version"):
                assert _table_exists(cur, table), f"{table} should exist"

            cols = _column_names(cur, "tasks")
            assert "owner_user_id" in cols
            assert "updated_by_user_id" in cols
        finally:
            conn.close()


# ── Test: v1 → v2 upgrade truncates existing tasks ──────────────────────


class TestV1ToV2Upgrade:
    """Verify that upgrading from v1 truncates existing task data."""

    def test_existing_tasks_truncated_on_upgrade(self):
        """When upgrading from schema version 1, existing tasks are deleted."""
        # Step 1: Set up a v1 database state using a direct connection.
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("SET FOREIGN_KEY_CHECKS = 0")
        cur.execute("DROP TABLE IF EXISTS task_assets")
        cur.execute("DROP TABLE IF EXISTS tasks")
        cur.execute("DROP TABLE IF EXISTS sessions")
        cur.execute("DROP TABLE IF EXISTS users")
        cur.execute("SET FOREIGN_KEY_CHECKS = 1")

        # Create schema_version table and record version 1
        cur.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version     INT UNSIGNED    NOT NULL,
                applied_at  DATETIME(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
                PRIMARY KEY (version)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
        cur.execute("DELETE FROM schema_version")
        cur.execute("INSERT INTO schema_version (version) VALUES (1)")

        # Create v1 tables (without owner_user_id)
        cur.execute("""
            CREATE TABLE tasks (
                id          INT UNSIGNED    NOT NULL AUTO_INCREMENT,
                name        VARCHAR(200)    NOT NULL,
                description TEXT            NULL,
                target_url  VARCHAR(2048)   NULL,
                status      VARCHAR(20)     NOT NULL DEFAULT 'draft',
                created_at  DATETIME(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
                updated_at  DATETIME(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
                                                    ON UPDATE CURRENT_TIMESTAMP(3),
                PRIMARY KEY (id),
                INDEX idx_tasks_list (status, created_at DESC)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
        cur.execute("""
            CREATE TABLE task_assets (
                id          INT UNSIGNED    NOT NULL AUTO_INCREMENT,
                task_id     INT UNSIGNED    NOT NULL,
                asset_type  VARCHAR(50)     NOT NULL,
                content     LONGTEXT        NULL,
                version     INT UNSIGNED    NOT NULL DEFAULT 1,
                created_at  DATETIME(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
                PRIMARY KEY (id),
                CONSTRAINT fk_task_assets_task_id
                    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
                INDEX idx_task_assets_latest (task_id, asset_type, version DESC),
                UNIQUE KEY uq_task_assets_version (task_id, asset_type, version)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)

        # Insert test data into v1 tasks
        cur.execute("INSERT INTO tasks (name) VALUES ('Old Task 1')")
        cur.execute("INSERT INTO tasks (name) VALUES ('Old Task 2')")
        conn.commit()

        # Verify data exists
        cur.execute("SELECT COUNT(*) AS cnt FROM tasks")
        assert cur.fetchone()["cnt"] == 2, "Should have 2 test tasks"

        # Close the setup connection to release all locks before migration
        cur.close()
        conn.close()

        # Step 2: Run migration (uses connection pool)
        from backend.database.migrations import run_migrations

        run_migrations()

        # Step 3: Verify results with a fresh connection
        conn2 = _get_conn()
        try:
            cur2 = conn2.cursor()

            # Verify tasks were truncated
            cur2.execute("SELECT COUNT(*) AS cnt FROM tasks")
            count = cur2.fetchone()["cnt"]
            assert count == 0, f"Expected 0 tasks after upgrade truncation, got {count}"

            # Verify schema is now v2
            cur2.execute("SELECT version FROM schema_version WHERE version = 2")
            assert cur2.fetchone() is not None, "schema_version should be 2"

            # Verify new columns exist
            cols = _column_names(cur2, "tasks")
            assert "owner_user_id" in cols
            assert "updated_by_user_id" in cols
        finally:
            conn2.close()

    def test_new_task_requires_owner_user_id(self):
        """After migration, inserting a task without owner_user_id fails."""
        from backend.database.migrations import run_migrations

        run_migrations()
        conn = _get_conn()
        try:
            cur = conn.cursor()
            with pytest.raises(pymysql.err.OperationalError):
                cur.execute("INSERT INTO tasks (name) VALUES ('No Owner')")
                conn.commit()
            conn.rollback()
        finally:
            conn.close()

    def test_new_task_with_owner_succeeds(self):
        """After migration, inserting a task with valid owner_user_id works."""
        from backend.database.migrations import run_migrations

        run_migrations()
        conn = _get_conn()
        try:
            cur = conn.cursor()
            # Create a user first (needed for FK)
            cur.execute(
                "INSERT INTO users (external_id, display_name) VALUES ('test_ext_1', 'Test User')"
            )
            user_id = cur.lastrowid

            # Insert task with owner
            cur.execute(
                "INSERT INTO tasks (owner_user_id, name) VALUES (%s, 'Owned Task')",
                (user_id,),
            )
            conn.commit()

            # Verify
            cur.execute("SELECT owner_user_id FROM tasks WHERE name = 'Owned Task'")
            row = cur.fetchone()
            assert row["owner_user_id"] == user_id
        finally:
            conn.close()
