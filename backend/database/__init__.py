"""Backend database module (MySQL)."""

from backend.database.db import close_connection, get_connection, get_cursor
from backend.database.models import ensure_schema

__all__ = [
    "close_connection",
    "ensure_schema",
    "get_connection",
    "get_cursor",
]
