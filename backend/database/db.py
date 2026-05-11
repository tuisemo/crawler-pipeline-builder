"""SQLite connection management for crawler workflow database."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DATABASE_PATH = _PROJECT_ROOT / "data" / "crawler_workflow.db"

_connection: sqlite3.Connection | None = None


def get_connection() -> sqlite3.Connection:
    """Get or create the module-level SQLite connection (WAL mode, foreign keys enabled)."""
    global _connection
    if _connection is None:
        _ensure_data_dir()
        _connection = sqlite3.connect(_DATABASE_PATH, check_same_thread=False)
        _connection.execute("PRAGMA journal_mode=WAL")
        _connection.execute("PRAGMA foreign_keys=ON")
    return _connection


def _ensure_data_dir() -> None:
    """Ensure the data directory exists."""
    data_dir = _PROJECT_ROOT / "data"
    data_dir.mkdir(exist_ok=True)


@contextmanager
def get_cursor() -> Generator[sqlite3.Cursor, None, None]:
    """Context manager for temporary cursor usage."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        yield cursor
    finally:
        cursor.close()


def close_connection() -> None:
    """Close the module-level SQLite connection."""
    global _connection
    if _connection is not None:
        _connection.close()
        _connection = None
