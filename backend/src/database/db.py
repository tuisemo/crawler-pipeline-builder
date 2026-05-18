"""MySQL connection pool management."""

from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Any, Generator

import pymysql
from dbutils.pooled_db import PooledDB
from pymysql.cursors import DictCursor

from core.settings import get_settings

_pool: PooledDB | None = None
_pool_lock = threading.Lock()


def _get_pool() -> PooledDB:
    """Lazy-init MySQL connection pool (thread-safe)."""
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                s = get_settings()
                _pool = PooledDB(
                    creator=pymysql,
                    maxconnections=s.db_pool_size,
                    maxshared=0,
                    blocking=True,
                    host=s.db_host,
                    port=int(s.db_port),
                    user=s.db_user,
                    password=s.db_password,
                    database=s.db_name,
                    charset="utf8mb4",
                    collation="utf8mb4_unicode_ci",
                    cursorclass=DictCursor,
                    autocommit=False,
                    connect_timeout=10,
                    read_timeout=30,
                )
    return _pool


@contextmanager
def get_cursor() -> Generator[DictCursor, None, None]:
    """Context-managed cursor with automatic commit/rollback."""
    pool = _get_pool()
    conn = pool.connection()
    cursor = conn.cursor()
    try:
        yield cursor
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def get_connection() -> Any:
    """Get a raw connection (for migrations)."""
    return _get_pool().connection()


def close_connection() -> None:
    """Shutdown hook: close the entire pool."""
    global _pool
    with _pool_lock:
        if _pool is not None:
            _pool.close()
            _pool = None
