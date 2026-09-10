import os
import sqlite3
from pathlib import Path

from flask import current_app

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "data" / "schema.sql"


def get_db_connection(database_path=None):
    """Create a thread-safe connection to SQLite with WAL mode enabled."""
    if database_path is None:
        try:
            database_path = current_app.config["DATABASE_PATH"]
        except RuntimeError:
            from app.config.settings import get_config

            database_path = get_config().DATABASE_PATH

    db_dir = os.path.dirname(database_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)

    conn = sqlite3.connect(database_path, timeout=20.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(database_path=None):
    """Initialize database tables using schema.sql."""
    conn = get_db_connection(database_path)
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema_sql = f.read()
    conn.executescript(schema_sql)
    conn.commit()
    conn.close()
