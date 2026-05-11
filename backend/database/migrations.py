"""Database migrations - creates all tables and indexes."""

from backend.database.db import get_connection
from backend.database.models import ALL_DDLStatements


def run_migrations() -> None:
    """Execute all DDL statements to set up the database schema."""
    conn = get_connection()
    cursor = conn.cursor()
    for statement in ALL_DDLStatements:
        cursor.execute(statement)
    conn.commit()
