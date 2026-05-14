"""Tests for database schema bootstrap.

Validates that ensure_schema() correctly:
- Creates all required tables (users, tasks, task_assets)
- Is idempotent (safe to call multiple times)
"""

from __future__ import annotations

import pymysql
import pytest
from pymysql.cursors import DictCursor

from backend.core.settings import get_settings
from backend.database.models import ALL_DDL, ensure_schema


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


class TestSchemaBootstrap:
    def test_users_table_created(self):
        ensure_schema()
        conn = _get_conn()
        try:
            cur = conn.cursor()
            assert _table_exists(cur, "users")
        finally:
            conn.close()

    def test_tasks_table_has_owner_columns(self):
        ensure_schema()
        conn = _get_conn()
        try:
            cur = conn.cursor()
            cols = _column_names(cur, "tasks")
            assert "owner_user_id" in cols
            assert "updated_by_user_id" in cols
        finally:
            conn.close()

    def test_no_legacy_auth_tables_in_ddl(self):
        ddl = "\n".join(ALL_DDL).lower()
        assert "create table if not exists sessions" not in ddl
        assert "create table if not exists auth_states" not in ddl
        assert "schema_version" not in ddl

    def test_running_twice_does_not_error(self):
        ensure_schema()
        ensure_schema()
