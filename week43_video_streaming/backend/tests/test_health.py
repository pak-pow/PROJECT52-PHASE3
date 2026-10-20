"""Integration tests for the system health check endpoint."""

from unittest.mock import patch

from flask.testing import FlaskClient


def test_health_check_endpoint(client: FlaskClient) -> None:
    """Verify that /api/health returns 200 with complete diagnostics."""
    response = client.get("/api/health")
    assert response.status_code == 200

    data = response.get_json()
    assert data["status"] == "ok"
    assert data["service"] == "PulseStream Video Streaming Platform"
    assert data["version"] == "1.0.0"
    assert data["database"] == "ok"
    assert "ffmpeg_available" in data
    assert "storage" in data
    assert "total_bytes" in data["storage"]


def test_health_check_db_failure_returns_503(client: FlaskClient) -> None:
    """Verify that /api/health returns 503 degraded when DB connection fails."""
    with patch(
        "app.routes.health.get_db_connection",
        side_effect=Exception("Database lock error"),
    ):
        response = client.get("/api/health")
        assert response.status_code == 503
        data = response.get_json()
        assert data["status"] == "degraded"
        assert "Database lock error" in data["database"]
