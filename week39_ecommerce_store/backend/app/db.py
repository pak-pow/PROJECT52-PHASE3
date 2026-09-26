import sqlite3
import time
from pathlib import Path

from flask import current_app, g, has_app_context

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "data" / "schema.sql"


def get_db(db_path=None):
    if db_path is None:
        if has_app_context():
            db_path = current_app.config.get("DATABASE_PATH")
        else:
            from app.config.settings import get_config

            db_path = get_config().DATABASE_PATH

    if db_path and db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    if has_app_context():
        if "_database" not in g:
            conn = sqlite3.connect(db_path or ":memory:", timeout=30.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute("PRAGMA busy_timeout = 30000;")
            g._database = conn
        return g._database

    conn = sqlite3.connect(db_path or ":memory:", timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA busy_timeout = 30000;")
    return conn


def close_db(e=None):
    if has_app_context():
        conn = g.pop("_database", None)
        if conn is not None:
            conn.close()


def init_db(db_path=None):
    conn = get_db(db_path=db_path)
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema_sql = f.read()
    conn.executescript(schema_sql)
    conn.commit()
    if not has_app_context():
        conn.close()


def query_db(query, args=(), one=False, db_path=None):
    conn = get_db(db_path=db_path)
    cur = conn.cursor()
    cur.execute(query, args)
    rows = cur.fetchall()
    cur.close()

    should_close = not has_app_context()
    if should_close:
        conn.close()

    results = [dict(row) for row in rows]
    return (results[0] if results else None) if one else results


def ping_db(db_path=None):
    start = time.perf_counter()
    try:
        conn = get_db(db_path=db_path)
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.fetchone()
        cur.close()
        if not has_app_context():
            conn.close()
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        return True, latency_ms
    except Exception:
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        return False, latency_ms
