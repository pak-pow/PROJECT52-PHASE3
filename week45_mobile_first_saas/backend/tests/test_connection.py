"""Unit tests for SQLite WAL connection manager and pragmas."""

import tempfile
from pathlib import Path

import pytest

from app.db.connection import close_db_connection, get_db_connection, init_db


def test_get_db_connection_in_memory():
    """Verify in-memory database connection sets up foreign keys and row factory."""
    conn = get_db_connection(":memory:")
    assert conn is not None
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys;")
    fk_status = cursor.fetchone()[0]
    cursor.close()
    conn.close()
    assert fk_status == 1


def test_get_db_connection_file_based():
    """Verify file SQLite connection enables WAL, NORMAL sync, and busy timeout."""
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "subfolder" / "wal_test.db"
        conn = get_db_connection(db_path)
        cursor = conn.cursor()

        cursor.execute("PRAGMA foreign_keys;")
        assert cursor.fetchone()[0] == 1

        cursor.execute("PRAGMA journal_mode;")
        journal_mode = cursor.fetchone()[0].lower()
        assert journal_mode == "wal"

        cursor.execute("PRAGMA synchronous;")
        sync_mode = cursor.fetchone()[0]
        assert sync_mode == 1  # 1 corresponds to NORMAL in SQLite

        cursor.execute("PRAGMA busy_timeout;")
        timeout = cursor.fetchone()[0]
        assert timeout == 5000

        cursor.close()
        conn.close()


def test_row_factory_access():
    """Verify row factory provides dictionary-like column access."""
    conn = get_db_connection(":memory:")
    cursor = conn.cursor()
    cursor.execute("SELECT 'pro' AS plan_name, 4900 AS price_cents;")
    row = cursor.fetchone()
    assert row["plan_name"] == "pro"
    assert row["price_cents"] == 4900
    cursor.close()
    conn.close()


def test_close_db_connection():
    """Verify close_db_connection handles active, None, and closed connections."""
    conn = get_db_connection(":memory:")
    close_db_connection(conn)
    # Closing already closed connection should not raise
    close_db_connection(conn)
    # Closing None should not raise
    close_db_connection(None)


def test_init_db_missing_schema_raises():
    """Verify init_db raises FileNotFoundError if schema file path is invalid."""
    with pytest.raises(FileNotFoundError):
        init_db(schema_path="non_existent_schema_file.sql", db_path=":memory:")
