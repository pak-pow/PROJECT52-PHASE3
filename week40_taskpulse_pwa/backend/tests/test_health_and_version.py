def test_health_check(client):
    """Verify health endpoint returns status healthy."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "healthy"
    assert "TaskPulse PWA API" in data["service"]
    assert "timestamp" in data


def test_version_check(client):
    """Verify version endpoint returns version specification."""
    response = client.get("/api/version")
    assert response.status_code == 200
    data = response.get_json()
    assert data["version"] == "1.0.0"
    assert data["pwa_sync_protocol"] == "v1"


def test_not_found_handler(client):
    """Verify 404 handler returns structured JSON."""
    response = client.get("/api/non-existent-route")
    assert response.status_code == 404
    data = response.get_json()
    assert data["status"] == "error"
    assert "Resource not found" in data["message"]
