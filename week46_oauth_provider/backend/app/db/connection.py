"""Thread-safe SQLite connection manager with WAL mode and busy timeouts."""

import sqlite3
from pathlib import Path
from typing import Optional

from flask import current_app, g

DEFAULT_SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent.parent / "data" / "schema.sql"
)


def get_db(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Obtain or reuse SQLite database connection for current request context."""
    if db_path is None:
        try:
            db_path = current_app.config.get("DATABASE_PATH", ":memory:")
        except RuntimeError:
            db_path = ":memory:"

    # If within Flask application context, cache in g
    if current_app and "db" in g and getattr(g, "_db_path", None) == db_path:
        return g.db

    conn = sqlite3.connect(
        db_path,
        detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row

    # Performance and concurrency pragmas
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA busy_timeout = 30000;")

    # Only enable WAL if using persistent file on disk
    if db_path != ":memory:" and not str(db_path).startswith(":memory:"):
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")

    if current_app:
        g.db = conn
        g._db_path = db_path

    return conn


def close_db(e: Optional[BaseException] = None) -> None:
    """Teardown database connection at the end of Flask request context."""
    db = getattr(g, "db", None)
    if db is not None:
        db.close()
        g.db = None


def init_db(
    db_path: Optional[str] = None,
    schema_path: Optional[Path] = None,
) -> sqlite3.Connection:
    """Initialize database tables, indexes, and constraints using schema.sql."""
    conn = get_db(db_path)
    target_schema = schema_path or DEFAULT_SCHEMA_PATH

    with open(target_schema, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    conn.executescript(schema_sql)
    conn.commit()
    return conn
