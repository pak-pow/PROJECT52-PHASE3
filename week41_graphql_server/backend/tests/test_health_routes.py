import tempfile
from pathlib import Path

from flask import abort

from app import create_app
from app.db import close_db, get_db, init_db


def test_health_check_endpoint(client):
    """Test /api/health endpoint returns 200 and healthy status."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "healthy"
    assert data["service"] == "PulseGraph GraphQL API"
    assert "timestamp" in data


def test_version_check_endpoint(client):
    """Test /api/version returns version info and engine metadata."""
    response = client.get("/api/version")
    assert response.status_code == 200
    data = response.get_json()
    assert data["version"] == "1.0.0"
    assert "graphql_engine" in data
    assert "PulseGraph" in data["service"]


def test_not_found_endpoint(client):
    """Test 404 handler returns JSON error structure."""
    response = client.get("/api/unknown_route")
    assert response.status_code == 404
    data = response.get_json()
    assert data["status"] == "error"
    assert data["message"] == "Resource not found"


def test_internal_server_error_handler(app):
    """Test 500 handler returns JSON error structure."""

    @app.route("/api/test_error")
    def trigger_error():
        abort(500)

    test_client = app.test_client()
    response = test_client.get("/api/test_error")
    assert response.status_code == 500
    data = response.get_json()
    assert data["status"] == "error"
    assert data["message"] == "Internal server error"


def test_create_app_default():
    """Test create_app without custom config uses default Config."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_db = str(Path(tmpdir) / "test.db")
        app_instance = create_app()
        assert app_instance is not None
        with app_instance.app_context():
            db = get_db(test_db)
            assert db is not None
            init_db()
            close_db()
