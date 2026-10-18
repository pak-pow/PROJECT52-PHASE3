"""Pytest configuration and common fixtures for PulsePad backend tests."""

import pytest
from flask import Flask
from flask_socketio import SocketIO

from app import create_app
from app.config.settings import TestingConfig
from app.db.connection import get_db_connection, init_db
from app.socket.editor_events import register_socket_events


@pytest.fixture
def app(tmp_path) -> Flask:
    """Create test application instance with temporary isolated database."""
    test_db = str(tmp_path / "test_pulsepad.db")
    test_app = create_app(TestingConfig)
    test_app.config["DB_PATH"] = test_db
    with test_app.app_context():
        init_db(
            db_path=test_db,
            schema_path=TestingConfig.DATA_DIR / "schema.sql",
        )
        yield test_app


@pytest.fixture
def client(app: Flask):
    """Create HTTP test client."""
    return app.test_client()


@pytest.fixture
def db_conn(app: Flask):
    """Create SQLite database connection to test app database."""
    with get_db_connection(app.config["DB_PATH"]) as conn:
        yield conn


@pytest.fixture
def socket_client(app: Flask):
    """Create SocketIO test client."""
    sio = SocketIO(app, async_mode="threading")
    register_socket_events(sio)
    return sio.test_client(app)
