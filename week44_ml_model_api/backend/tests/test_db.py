"""Unit tests for configuration environments and SQLite connection manager."""

import sqlite3
from pathlib import Path

import pytest

from app.config.settings import (
    DevelopmentConfig,
    ProductionConfig,
    TestingConfig,
    get_config,
)
from app.db.connection import close_db_connection, get_db_connection, init_db


def test_get_config_environments() -> None:
    """Verify configuration selection across environment names."""
    assert get_config("development") is DevelopmentConfig
    assert get_config("testing") is TestingConfig
    assert get_config("production") is ProductionConfig
    assert get_config("unknown_env") is DevelopmentConfig


def test_db_connection_foreign_keys_and_wal(temp_dir: Path) -> None:
    """Verify SQLite WAL mode and foreign key constraints are applied."""
    db_file = temp_dir / "wal_test.db"
    conn = get_db_connection(db_file)

    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys;")
    fk_enabled = cursor.fetchone()[0]
    assert fk_enabled == 1

    cursor.execute("PRAGMA journal_mode;")
    journal = cursor.fetchone()[0].lower()
    assert journal == "wal"

    conn.close()


def test_memory_db_connection() -> None:
    """Verify in-memory SQLite connection configuration."""
    conn = get_db_connection(":memory:")
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys;")
    assert cursor.fetchone()[0] == 1
    conn.close()


def test_init_db_creates_tables(temp_dir: Path) -> None:
    """Verify database initialization builds all declared tables and indexes."""
    db_file = temp_dir / "init_test.db"
    init_db(db_path=db_file)

    conn = get_db_connection(db_file)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
    tables = [row["name"] for row in cursor.fetchall()]
    conn.close()

    assert "models" in tables
    assert "model_versions" in tables
    assert "prediction_logs" in tables


def test_init_db_missing_schema_raises_error(temp_dir: Path) -> None:
    """Verify FileNotFoundError is raised when schema file does not exist."""
    missing_file = temp_dir / "missing_schema.sql"
    with pytest.raises(FileNotFoundError):
        init_db(schema_path=missing_file, db_path=temp_dir / "test.db")


def test_close_db_handles_none_and_open(temp_dir: Path) -> None:
    """Verify safe closure of connections including None references."""
    close_db_connection(None)

    db_file = temp_dir / "close_test.db"
    conn = get_db_connection(db_file)
    close_db_connection(conn)
    with pytest.raises(sqlite3.ProgrammingError):
        conn.cursor()
