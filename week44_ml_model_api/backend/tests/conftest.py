"""Pytest fixtures and test environment setup for PulseInfer."""

from pathlib import Path
from typing import Generator

import pytest
from flask import Flask
from flask.testing import FlaskClient, FlaskCliRunner

from app import create_app
from app.db.connection import init_db
from app.services.storage_service import StorageService


@pytest.fixture
def temp_dir(tmp_path: Path) -> Path:
    """Provide a clean temporary directory for isolated test execution."""
    return tmp_path


@pytest.fixture
def test_db_path(temp_dir: Path) -> Path:
    """Initialize an isolated test database with table schemas."""
    db_file = temp_dir / "test_pulseinfer.db"
    init_db(db_path=db_file)
    return db_file


@pytest.fixture
def app(temp_dir: Path, test_db_path: Path) -> Generator[Flask, None, None]:
    """Create and configure a Flask application instance for testing."""
    vault_dir = temp_dir / "models_vault"
    storage = StorageService(vault_dir=vault_dir)
    storage.ensure_storage_dirs()

    test_config = {
        "TESTING": True,
        "DEBUG": True,
        "DB_PATH": test_db_path,
        "MODELS_VAULT_DIR": vault_dir,
    }

    application = create_app(config=test_config)

    with application.app_context():
        yield application

    registry = application.extensions.get("registry")
    if registry:
        registry.shutdown()


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    """Flask test client for issuing HTTP requests."""
    return app.test_client()


@pytest.fixture
def runner(app: Flask) -> FlaskCliRunner:
    """Flask CLI test runner."""
    return app.test_cli_runner()
