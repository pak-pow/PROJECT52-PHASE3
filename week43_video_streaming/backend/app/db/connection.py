"""SQLite connection manager with WAL mode and foreign key enforcement."""

import sqlite3
from pathlib import Path
from typing import Optional, Union

from app.config.settings import Config


def get_db_connection(
    db_path: Optional[Union[str, Path]] = None,
) -> sqlite3.Connection:
    """Create and return a configured SQLite database connection.

    Enables WAL journal mode for persistent databases and activates foreign key
    constraints across all connections.
    """
    target_path = Path(db_path) if db_path is not None else Config.DB_PATH
    path_str = str(target_path)

    if path_str != ":memory:":
        target_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(path_str, check_same_thread=False)
    conn.row_factory = sqlite3.Row

    # Always enforce foreign keys
    conn.execute("PRAGMA foreign_keys = ON;")

    # Apply WAL mode for persistent files
    if path_str != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL;")

    return conn


def init_db(
    db_path: Optional[Union[str, Path]] = None,
    schema_path: Optional[Union[str, Path]] = None,
) -> None:
    """Initialize the database schema from the SQL schema definition file."""
    schema_file = Path(schema_path) if schema_path is not None else Config.SCHEMA_PATH
    if not schema_file.exists():
        raise FileNotFoundError(f"Database schema file not found: {schema_file}")

    with open(schema_file, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    conn = get_db_connection(db_path)
    try:
        conn.executescript(schema_sql)
        conn.commit()
    finally:
        conn.close()


def close_db(conn: Optional[sqlite3.Connection]) -> None:
    """Safely close an open database connection."""
    if conn is not None:
        try:
            conn.close()
        except sqlite3.Error:
            pass
