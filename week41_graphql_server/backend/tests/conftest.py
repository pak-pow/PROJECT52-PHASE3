import os

import pytest

from app import create_app
from app.config.settings import TestingConfig
from app.db import close_db, get_db, init_db
from data.seed import seed_database


@pytest.fixture
def app():
    """Create and configure a clean application instance for testing."""
    test_db_path = TestingConfig.DB_PATH
    if os.path.exists(test_db_path):
        try:
            os.remove(test_db_path)
        except OSError:
            pass

    test_app = create_app(TestingConfig)
    with test_app.app_context():
        init_db(test_app)
        seed_database(get_db())
        yield test_app
        close_db()

    if os.path.exists(test_db_path):
        try:
            os.remove(test_db_path)
        except OSError:
            pass


@pytest.fixture
def client(app):
    """Test client for issuing HTTP requests."""
    return app.test_client()


@pytest.fixture
def runner(app):
    """CLI runner for testing commands."""
    return app.test_cli_runner()
