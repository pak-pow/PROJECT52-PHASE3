"""Pytest configuration and test fixtures for Docker Pulse."""

from pathlib import Path

import pytest

from app import create_app
from app.cache import cache
from app.db import init_db

TEST_DB_PATH = Path(__file__).resolve().parent / "test_tasks.db"


@pytest.fixture
def app():
    """Create a Flask application configured for testing with isolated test database."""
    test_db_url = f"sqlite:///{TEST_DB_PATH.as_posix()}"
    app_instance = create_app("testing", init_database=False)
    app_instance.config["DATABASE_URL"] = test_db_url

    with app_instance.app_context():
        init_db(test_db_url)
        cache.clear()
        yield app_instance
        cache.clear()

    if TEST_DB_PATH.exists():
        try:
            TEST_DB_PATH.unlink()
        except Exception:
            pass


@pytest.fixture
def client(app):
    """Test HTTP client."""
    return app.test_client()
