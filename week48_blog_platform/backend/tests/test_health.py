"""Tests for health check endpoint, static asset delivery, and security headers."""


def test_health_endpoint_returns_200(client):
    """Verify GET /api/health reports healthy service and connected database."""
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"
    assert data["service"] == "PulsePress"
    assert data["version"] == "1.0.0"


def test_static_index_serving(client):
    """Verify root / serves the frontend single page HTML."""
    res = client.get("/")
    assert res.status_code == 200
    assert b"PulsePress" in res.data
    assert b"<!DOCTYPE html>" in res.data


def test_static_css_asset_serving(client):
    """Verify /src/assets/base.css is served with correct CSS content."""
    res = client.get("/src/assets/base.css")
    assert res.status_code == 200
    assert b"--font-sans" in res.data


def test_cors_and_security_headers(client):
    """Verify security and CORS headers are injected on all responses."""
    res = client.get("/api/health")
    assert res.headers.get("X-Content-Type-Options") == "nosniff"
    assert res.headers.get("X-Frame-Options") == "SAMEORIGIN"
    assert res.headers.get("Access-Control-Allow-Origin") == "*"
