"""Pytest configuration and test fixtures for Docker Pulse."""

import sys
from pathlib import Path

import pytest

# Ensure backend package is on sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app import create_app  # noqa: E402
from app.cache import cache  # noqa: E402
from app.db import init_db  # noqa: E402

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
