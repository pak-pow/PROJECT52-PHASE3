"""Unit tests for the health check and static frontend endpoints."""

from unittest.mock import patch

from flask.testing import FlaskClient


def test_health_check_endpoint(client: FlaskClient) -> None:
    """Verify health check returns status 200 with database and storage stats."""
    response = client.get("/api/health")
    assert response.status_code == 200

    data = response.get_json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"
    assert data["service"] == "pulseinfer-ml-api"
    assert "vault" in data


def test_health_check_db_failure_returns_503(client: FlaskClient) -> None:
    """Verify health check returns status 503 when database connectivity fails."""
    with patch("app.routes.health.get_db_connection") as mock_conn:
        mock_conn.side_effect = Exception("Simulated SQLite disk I/O error")

        response = client.get("/api/health")
        assert response.status_code == 503

        data = response.get_json()
        assert data["status"] == "degraded"
        assert "unhealthy" in data["database"]


def test_static_frontend_routes(client: FlaskClient) -> None:
    """Verify single-page frontend shell and static assets are served properly."""
    resp_index = client.get("/")
    assert resp_index.status_code == 200
    assert "PulseInfer" in resp_index.get_data(as_text=True)

    resp_css = client.get("/src/assets/base.css")
    assert resp_css.status_code == 200

    resp_js = client.get("/src/app.js")
    assert resp_js.status_code == 200

    resp_pub = client.get("/public/index.html")
    assert resp_pub.status_code == 200

    # Test index fallback when index.html is missing
    with patch("app.routes.static_routes.Path.exists", return_value=False):
        resp_fallback = client.get("/")
        assert resp_fallback.status_code == 200
        assert "PulseInfer ML Model API is running" in resp_fallback.get_data(
            as_text=True
        )
