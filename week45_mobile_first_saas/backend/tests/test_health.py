"""Integration tests for HTTP health check, security headers, and static routes."""

import sqlite3

from app.config.settings import (
    DevelopmentConfig,
    ProductionConfig,
    TestingConfig,
    get_config,
)


def test_health_endpoint_healthy(client):
    """Verify /api/health responds with 200 and healthy status."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"
    assert data["service"] == "PulseSub"
    assert data["version"] == "1.0.0"
    assert "timestamp" in data


def test_health_degraded_when_db_fails(app, monkeypatch):
    """Verify /api/health returns 503 and degraded status when database is invalid."""

    def mock_fail(*args, **kwargs):
        raise sqlite3.OperationalError("Unable to open database file")

    monkeypatch.setattr("app.routes.health.get_db_connection", mock_fail)
    test_client = app.test_client()
    response = test_client.get("/api/health")
    assert response.status_code == 503
    data = response.get_json()
    assert data["status"] == "degraded"
    assert "unhealthy" in data["database"]


def test_security_headers_present(client):
    """Verify standard security and CORS headers are injected on responses."""
    response = client.get("/api/health")
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "SAMEORIGIN"
    assert response.headers.get("Access-Control-Allow-Origin") == "*"


def test_static_index_route(client):
    """Verify root / serves the frontend index.html."""
    response = client.get("/")
    assert response.status_code == 200
    assert b"PulseSub - Mobile-First SaaS Platform" in response.data


def test_static_css_route(client):
    """Verify /css/base.css serves the mobile-first stylesheet."""
    response = client.get("/css/base.css")
    assert response.status_code == 200
    assert b"PulseSub Mobile-First SaaS Design System" in response.data


def test_static_js_route(client):
    """Verify /js/app.js serves frontend script."""
    response = client.get("/js/app.js")
    assert response.status_code == 200
    assert b"PulseSub Mobile-First Frontend Application Controller" in response.data


def test_config_retrieval():
    """Verify environment configuration factory resolves appropriate classes."""
    assert get_config("development") == DevelopmentConfig
    assert get_config("testing") == TestingConfig
    assert get_config("production") == ProductionConfig
    assert get_config("unknown_environment") == DevelopmentConfig
