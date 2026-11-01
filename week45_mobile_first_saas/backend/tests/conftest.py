"""Pytest configuration and fixtures for PulseSub test suite."""

import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Generator

import pytest

# Ensure backend package is on sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app import create_app  # noqa: E402
from app.db.connection import get_db_connection, init_db  # noqa: E402


@pytest.fixture
def temp_db_path() -> Generator[Path, None, None]:
    """Yield a temporary database path and cleanly tear down afterwards."""
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "test_pulsesub.db"
        init_db(db_path=db_path, seed_defaults=True)
        yield db_path


@pytest.fixture
def db_conn(temp_db_path: Path) -> Generator[sqlite3.Connection, None, None]:
    """Yield an open database connection pointing to the seeded test database."""
    conn = get_db_connection(temp_db_path)
    yield conn
    conn.close()


@pytest.fixture
def app(temp_db_path: Path):
    """Yield a Flask application configured with test database."""
    test_config = {
        "TESTING": True,
        "DEBUG": True,
        "DB_PATH": str(temp_db_path),
        "SECRET_KEY": "test_secret_key_pulse_2026",
        "WEBHOOK_SIGNING_SECRET": "whsec_test_mock_secret_2026",
    }
    app_instance = create_app(config=test_config)
    return app_instance


@pytest.fixture
def client(app):
    """Yield a test HTTP client for API requests."""
    return app.test_client()
