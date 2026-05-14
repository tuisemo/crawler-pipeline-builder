"""Tests for database migration (v1 → v2 schema upgrade).

Validates that run_migrations() correctly:
- Creates users table
- Adds owner_user_id and updated_by_user_id to tasks
- Records schema version 2
- Is idempotent
"""

from __future__ import annotations

import pymysql
import pytest
from pymysql.cursors import DictCursor

from backend.core.settings import get_settings
from backend.database.models import ALL_DDL, SCHEMA_VERSION


def _get_conn() -> pymysql.Connection:
    s = get_settings()
    return pymysql.connect(
        host=s.db_host,
        port=int(s.db_port),
        user=s.db_user,
        password=s.db_password,
        database=s.db_name,
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=False,
    )


def _table_exists(cursor, name: str) -> bool:
    cursor.execute("SHOW TABLES LIKE %s", (name,))
    return cursor.fetchone() is not None


def _column_names(cursor, table: str) -> set[str]:
    cursor.execute(f"DESCRIBE {table}")
    return {row["Field"] for row in cursor.fetchall()}


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


class TestFreshInstall:
    def test_users_table_created(self):
        from backend.database.migrations import run_migrations
        run_migrations()
        conn = _get_conn()
        try:
            cur = conn.cursor()
            assert _table_exists(cur, "users")
        finally:
            conn.close()

    def test_tasks_table_has_owner_columns(self):
        from backend.database.migrations import run_migrations
        run_migrations()
        conn = _get_conn()
        try:
            cur = conn.cursor()
            cols = _column_names(cur, "tasks")
            assert "owner_user_id" in cols
            assert "updated_by_user_id" in cols
        finally:
            conn.close()

    def test_schema_version_is_current_or_newer(self):
        from backend.database.migrations import run_migrations
        run_migrations()
        conn = _get_conn()
        try:
            cur = conn.cursor()
            cur.execute("SELECT version FROM schema_version ORDER BY version")
            versions = [row["version"] for row in cur.fetchall()]
            assert versions
            assert max(versions) >= SCHEMA_VERSION
        finally:
            conn.close()

    def test_migrations_do_not_define_legacy_auth_tables(self):
        ddl = "\n".join(ALL_DDL).lower()
        assert "create table if not exists sessions" not in ddl
        assert "create table if not exists auth_states" not in ddl


class TestIdempotency:
    def test_running_twice_does_not_error(self):
        from backend.database.migrations import run_migrations
        run_migrations()
        run_migrations()

    def test_current_schema_version_present_after_second_run(self):
        from backend.database.migrations import run_migrations
        run_migrations()
        run_migrations()
        conn = _get_conn()
        try:
            cur = conn.cursor()
            cur.execute("SELECT MAX(version) AS max_version FROM schema_version")
            assert cur.fetchone()["max_version"] >= SCHEMA_VERSION
        finally:
            conn.close()
