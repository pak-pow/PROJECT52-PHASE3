import pytest
from flask import Flask
from flask_socketio import SocketIO

from app import create_app
from app.config.settings import TestingConfig
from app.db.connection import get_db_connection, init_db
from app.socket.editor_events import register_socket_events


@pytest.fixture
def app() -> Flask:
    """Create test application instance with in-memory database."""
    test_app = create_app(TestingConfig)
    with test_app.app_context():
        init_db(
            db_path=":memory:",
            schema_path=TestingConfig.DATA_DIR / "schema.sql",
        )
        yield test_app


@pytest.fixture
def client(app: Flask):
    """Create HTTP test client."""
    return app.test_client()


@pytest.fixture
def db_conn():
    """Create in-memory SQLite database connection with schema."""
    conn = get_db_connection(":memory:")
    schema_path = TestingConfig.DATA_DIR / "schema.sql"
    with open(schema_path, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def socket_client(app: Flask):
    """Create SocketIO test client."""
    sio = SocketIO(app, async_mode="threading")
    register_socket_events(sio)
    return sio.test_client(app)
