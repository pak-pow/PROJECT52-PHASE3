"""Unit tests for SQLite database connection, initialization, and configuration."""

import sqlite3
from pathlib import Path

import pytest

from app.config.settings import DevelopmentConfig, TestingConfig, get_config
from app.db.connection import close_db, get_db_connection, init_db


def test_get_config_environments() -> None:
    """Verify configuration selection based on environment name."""
    dev_cfg = get_config("development")
    assert isinstance(dev_cfg, DevelopmentConfig)
    assert dev_cfg.DEBUG is True

    test_cfg = get_config("testing")
    assert isinstance(test_cfg, TestingConfig)
    assert test_cfg.TESTING is True


def test_db_connection_foreign_keys_and_wal(temp_dir: Path) -> None:
    """Verify that get_db_connection enables WAL mode and enforces foreign keys."""
    db_file = temp_dir / "wal_test.db"
    conn = get_db_connection(db_path=db_file)
    try:
        # Check WAL journal mode
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode;")
        row = cursor.fetchone()
        assert row[0].lower() == "wal"

        # Check foreign keys enabled
        cursor.execute("PRAGMA foreign_keys;")
        row = cursor.fetchone()
        assert row[0] == 1
    finally:
        conn.close()


def test_memory_db_connection() -> None:
    """Verify that in-memory database connection handles foreign keys cleanly."""
    conn = get_db_connection(db_path=":memory:")
    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys;")
        row = cursor.fetchone()
        assert row[0] == 1
    finally:
        conn.close()


def test_init_db_creates_tables(test_conn: sqlite3.Connection) -> None:
    """Verify that init_db creates all expected tables."""
    cursor = test_conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
    tables = [row["name"] for row in cursor.fetchall()]

    assert "categories" in tables
    assert "videos" in tables
    assert "video_renditions" in tables
    assert "transcoding_jobs" in tables


def test_init_db_missing_schema_raises_error(temp_dir: Path) -> None:
    """Verify FileNotFoundError when schema file path does not exist."""
    missing_schema = temp_dir / "nonexistent_schema.sql"
    with pytest.raises(FileNotFoundError):
        init_db(db_path=temp_dir / "db.sqlite", schema_path=missing_schema)


def test_close_db_handles_none_and_open() -> None:
    """Verify close_db closes open connection and ignores None."""
    close_db(None)
    conn = get_db_connection(":memory:")
    close_db(conn)
    # Calling close again on already closed connection should not throw
    close_db(conn)
