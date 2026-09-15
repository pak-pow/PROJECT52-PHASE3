"""Database abstraction layer supporting dual PostgreSQL and SQLite engines.

Automatically resolves the driver based on DATABASE_URL, normalizes parameter
placeholders (? vs %s), handles table initialization, and provides health checks.
"""

import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor

    HAS_PSYCOPG2 = True
except ImportError:  # pragma: no cover
    HAS_PSYCOPG2 = False
    RealDictCursor = None


SCHEMA_PATH = Path(__file__).resolve().parent.parent / "data" / "schema.sql"


def is_postgres(db_url: str) -> bool:
    """Determine whether the provided database URL targets PostgreSQL."""
    return db_url.startswith("postgresql://") or db_url.startswith("postgres://")


@contextmanager
def get_db_connection(db_url: Optional[str] = None):
    """Context manager providing a database connection and automatic closing.

    Yields a connection configured with dictionary-like row access.
    """
    if db_url is None:
        db_url = os.getenv("DATABASE_URL", "sqlite:///data/tasks.db")

    if is_postgres(db_url):
        if not HAS_PSYCOPG2:  # pragma: no cover
            raise RuntimeError("psycopg2 is required for PostgreSQL connections.")
        conn = psycopg2.connect(db_url, cursor_factory=RealDictCursor)
        try:
            yield conn
        finally:
            conn.close()
    else:
        # SQLite connection
        sqlite_path = db_url.replace("sqlite:///", "")
        if sqlite_path != ":memory:":
            Path(sqlite_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(sqlite_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        if sqlite_path != ":memory:":
            conn.execute("PRAGMA journal_mode = WAL;")
        try:
            yield conn
        finally:
            conn.close()


def execute_query(
    query: str,
    params: Optional[Tuple[Any, ...]] = None,
    db_url: Optional[str] = None,
    commit: bool = False,
    fetch_one: bool = False,
    fetch_all: bool = False,
) -> Any:
    """Execute a database query with parameter placeholder normalization.

    Translates '?' placeholders to '%s' when executing against PostgreSQL.
    Returns single row dict, list of row dicts, lastrowid, or affected row count.
    """
    if db_url is None:
        db_url = os.getenv("DATABASE_URL", "sqlite:///data/tasks.db")
    if params is None:
        params = ()

    postgres_mode = is_postgres(db_url)
    executable_query = query
    if postgres_mode:
        executable_query = query.replace("?", "%s")

    with get_db_connection(db_url) as conn:
        cursor = conn.cursor()
        cursor.execute(executable_query, params)

        result: Any = None
        if fetch_one:
            row = cursor.fetchone()
            result = dict(row) if row else None
        elif fetch_all:
            rows = cursor.fetchall()
            result = [dict(r) for r in rows]
        elif commit:
            conn.commit()
            if hasattr(cursor, "lastrowid") and cursor.lastrowid:
                result = cursor.lastrowid
            else:
                result = cursor.rowcount

        cursor.close()
        return result


def init_db(db_url: Optional[str] = None, retries: int = 5, delay: float = 1.0) -> bool:
    """Initialize database tables and indexes from schema.sql with retry support."""
    if db_url is None:
        db_url = os.getenv("DATABASE_URL", "sqlite:///data/tasks.db")

    if not SCHEMA_PATH.exists():
        raise FileNotFoundError(f"Schema file not found at {SCHEMA_PATH}")

    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    postgres_mode = is_postgres(db_url)

    if postgres_mode:
        # Convert SQLite AUTOINCREMENT syntax to PostgreSQL SERIAL PRIMARY KEY
        schema_sql = schema_sql.replace(
            "INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY"
        )
        schema_sql = schema_sql.replace("REAL NOT NULL", "DOUBLE PRECISION NOT NULL")

    last_error: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        try:
            with get_db_connection(db_url) as conn:
                cursor = conn.cursor()
                if postgres_mode:
                    cursor.execute(schema_sql)
                else:
                    cursor.executescript(schema_sql)
                conn.commit()
                cursor.close()
            return True
        except Exception as err:
            last_error = err
            if attempt < retries:
                time.sleep(delay)
            else:
                raise last_error

    return True


def check_db_health(db_url: Optional[str] = None) -> Dict[str, Any]:
    """Verify database responsiveness and measure query latency."""
    if db_url is None:
        db_url = os.getenv("DATABASE_URL", "sqlite:///data/tasks.db")

    engine = "postgresql" if is_postgres(db_url) else "sqlite"
    start_time = time.perf_counter()

    try:
        with get_db_connection(db_url) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1;")
            cursor.fetchone()
            cursor.close()
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        return {
            "status": "healthy",
            "engine": engine,
            "latency_ms": latency_ms,
        }
    except Exception as exc:
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        return {
            "status": "unhealthy",
            "engine": engine,
            "latency_ms": latency_ms,
            "error": str(exc),
        }
