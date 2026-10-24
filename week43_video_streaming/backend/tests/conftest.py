"""Pytest shared fixtures for PulseStream backend tests."""

import tempfile
from pathlib import Path
from typing import Generator

import pytest
from flask import Flask
from flask.testing import FlaskClient

from app import create_app
from app.db.connection import get_db_connection, init_db
from app.services.storage_service import StorageService


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Provide a temporary directory for tests and cleanly remove it."""
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


@pytest.fixture
def test_db_path(temp_dir: Path) -> Path:
    """Provide an isolated file-based SQLite database for testing WAL mode."""
    db_file = temp_dir / "test_pulsestream.db"
    init_db(db_path=db_file)
    return db_file


@pytest.fixture
def test_conn(test_db_path: Path):
    """Provide a database connection connected to isolated test db."""
    conn = get_db_connection(db_path=test_db_path)
    yield conn
    conn.close()


@pytest.fixture
def test_storage(temp_dir: Path) -> StorageService:
    """Provide a storage service configured within temporary directory."""
    media_dir = temp_dir / "media"
    return StorageService(media_dir=media_dir)


@pytest.fixture
def app(test_db_path: Path, temp_dir: Path) -> Flask:
    """Provide a configured test Flask application."""
    media_dir = temp_dir / "media"
    test_cfg = {
        "TESTING": True,
        "DEBUG": True,
        "DB_PATH": test_db_path,
        "MEDIA_DIR": media_dir,
    }
    app_instance = create_app(config=test_cfg)
    return app_instance


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    """Provide a test client for API requests."""
    return app.test_client()
