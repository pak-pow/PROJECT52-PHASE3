"""Tests for database connection manager and SQLite settings."""

import tempfile
from pathlib import Path

from app.db.connection import (
    close_db_connection,
    get_db_connection,
    init_db,
)


def test_wal_mode_enabled_on_disk():
    """Verify WAL journal mode is active on persistent disk databases."""
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "test_wal.db"
        init_db(db_path=db_path, seed_defaults=False)

        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode;")
        mode = cursor.fetchone()[0]
        cursor.execute("PRAGMA foreign_keys;")
        fks = cursor.fetchone()[0]
        cursor.execute("PRAGMA busy_timeout;")
        timeout = cursor.fetchone()[0]
        conn.close()

        assert mode.lower() == "wal"
        assert fks == 1
        assert timeout == 5000


def test_in_memory_connection():
    """Verify in-memory database connection executes cleanly."""
    conn = get_db_connection(":memory:")
    cursor = conn.cursor()
    cursor.execute("SELECT 1;")
    res = cursor.fetchone()[0]
    conn.close()
    assert res == 1


def test_close_db_connection_handles_none_and_exceptions():
    """Verify safe closure handles None and already-closed connections."""
    close_db_connection(None)

    conn = get_db_connection(":memory:")
    conn.close()
    # Closing twice should not raise unhandled exception
    close_db_connection(conn)
