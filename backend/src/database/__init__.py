"""Backend database module (MySQL)."""

from database.db import close_connection, get_connection, get_cursor
from database.models import ensure_schema

__all__ = [
    "close_connection",
    "ensure_schema",
    "get_connection",
    "get_cursor",
]
