import os
import pytest
from app import create_app
from app.config.settings import TestingConfig
from app.db import init_db


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
