"""Database connection and initialization module for PulsePad."""

import sqlite3
from pathlib import Path
from typing import Optional

from app.config.settings import Config


def get_db_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Create and return a database connection configured with WAL and foreign keys."""
    target_path = db_path or Config.DB_PATH
    conn = sqlite3.connect(target_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    if target_path != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL;")
    return conn


def init_db(db_path: Optional[str] = None, schema_path: Optional[str] = None) -> None:
    """Initialize database tables from schema.sql."""
    target_db = db_path or Config.DB_PATH
    target_schema = schema_path or (Config.DATA_DIR / "schema.sql")

    schema_file = Path(target_schema)
    if not schema_file.exists():
        raise FileNotFoundError(f"Schema file not found at {schema_file}")

    with get_db_connection(target_db) as conn:
        with open(schema_file, "r", encoding="utf-8") as f:
            conn.executescript(f.read())
        conn.commit()
