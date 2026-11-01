"""Database connection manager for PulseSub with SQLite WAL mode."""

import json
import sqlite3
from pathlib import Path
from typing import Optional, Union

from app.config.settings import Config
from data.seed import DEFAULT_PLANS


def get_db_connection(
    db_path: Optional[Union[str, Path]] = None,
) -> sqlite3.Connection:
    """Create and configure a SQLite connection with WAL mode and foreign keys."""
    target_path = db_path if db_path is not None else Config.DB_PATH
    is_memory = str(target_path) == ":memory:"

    if not is_memory:
        p = Path(target_path)
        p.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(
        str(target_path),
        timeout=10.0,
        detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
    )
    conn.row_factory = sqlite3.Row

    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON;")
    if not is_memory:
        cursor.execute("PRAGMA journal_mode = WAL;")
        cursor.execute("PRAGMA synchronous = NORMAL;")
    cursor.execute("PRAGMA busy_timeout = 5000;")
    cursor.close()

    return conn


def init_db(
    schema_path: Optional[Union[str, Path]] = None,
    db_path: Optional[Union[str, Path]] = None,
    seed_defaults: bool = True,
) -> None:
    """Initialize database tables, indexes, and initial plan tiers."""
    schema_file = Path(schema_path or Config.SCHEMA_PATH)
    if not schema_file.exists():
        raise FileNotFoundError(f"Database schema file not found: {schema_file}")

    schema_sql = schema_file.read_text(encoding="utf-8")
    conn = get_db_connection(db_path=db_path)
    try:
        conn.executescript(schema_sql)
        if seed_defaults:
            cursor = conn.cursor()
            for plan in DEFAULT_PLANS:
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO plans (
                        id, name, tier, price_monthly_cents, price_annual_cents,
                        limits_json, features_json, is_active
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        plan["id"],
                        plan["name"],
                        plan["tier"],
                        plan["price_monthly_cents"],
                        plan["price_annual_cents"],
                        json.dumps(plan["limits"]),
                        json.dumps(plan["features"]),
                        plan["is_active"],
                    ),
                )
        conn.commit()
    finally:
        conn.close()


def close_db_connection(conn: Optional[sqlite3.Connection]) -> None:
    """Safely close an open database connection."""
    if conn is not None:
        try:
            conn.close()
        except sqlite3.Error:
            pass
