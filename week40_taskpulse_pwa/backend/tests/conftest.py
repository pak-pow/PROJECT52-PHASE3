import pytest
from app import create_app
from app.config.settings import TestingConfig
from app.db import init_db


@pytest.fixture
def app():
    """Create and configure a clean application instance for testing."""
    test_app = create_app(TestingConfig)
    with test_app.app_context():
        init_db(test_app)
        yield test_app


@pytest.fixture
def client(app):
    """Test client for issuing HTTP requests."""
    return app.test_client()


@pytest.fixture
def runner(app):
    """CLI runner for testing commands."""
    return app.test_cli_runner()
