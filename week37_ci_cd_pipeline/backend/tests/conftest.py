import os
import sys
from pathlib import Path

import pytest

# Ensure backend package is on sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app import create_app  # noqa: E402
from app.config.settings import TestingConfig  # noqa: E402
from app.db import init_db  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """Ensure clean test database directory and schema exists."""
    db_path = TestingConfig.DATABASE_PATH
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
        except OSError:
            pass

    init_db(db_path)
    yield
    # Teardown after test session
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
        except OSError:
            pass


@pytest.fixture
def app():
    """Create a test application instance configured with TestingConfig."""
    app_instance = create_app(TestingConfig)
    return app_instance


@pytest.fixture
def client(app):
    """Test client for making HTTP requests to the test application."""
    return app.test_client()
