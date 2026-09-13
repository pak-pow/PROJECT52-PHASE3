"""Unit tests for health, version, and readiness endpoints."""

from unittest.mock import patch


def test_health_check_endpoint(client):
    """Verify /api/v1/health returns 200 with service metadata and uptime."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "healthy"
    assert data["service"] == "docker-pulse-api"
    assert "uptime_seconds" in data
    assert data["environment"] == "testing"
    assert "hostname" in data


def test_version_endpoint(client):
    """Verify /api/v1/version returns semantic version and commit hash."""
    response = client.get("/api/v1/version")
    assert response.status_code == 200
    data = response.get_json()
    assert data["version"] == "1.0.0"
    assert "app_name" in data
    assert "commit_sha" in data


def test_readiness_probe_healthy(client):
    """Verify /api/v1/ready returns 200 when all dependencies are healthy."""
    response = client.get("/api/v1/ready")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "ready"
    assert data["database"]["status"] == "healthy"
    assert data["cache"]["status"] == "healthy"


def test_readiness_probe_degraded(client):
    """Verify /api/v1/ready returns 503 when database is unhealthy."""
    with patch("app.routes.health_routes.check_db_health") as mock_db:
        mock_db.return_value = {
            "status": "unhealthy",
            "engine": "sqlite",
            "error": "Connection refused",
        }
        response = client.get("/api/v1/ready")
        assert response.status_code == 503
        data = response.get_json()
        assert data["status"] == "degraded"
