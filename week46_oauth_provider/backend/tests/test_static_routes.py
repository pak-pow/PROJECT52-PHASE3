"""Tests for static asset and frontend routing in PulseAuth."""

from pathlib import Path

import app.routes.static_routes as sr


def test_index_route_success(client):
    """Test GET / serves the primary index.html shell."""
    response = client.get("/")
    assert response.status_code == 200
    assert b"PulseAuth" in response.data
    assert b"OAuth 2.0 Playground" in response.data


def test_index_route_not_found(client, monkeypatch):
    """Test GET / returns 404 when index.html is missing."""
    monkeypatch.setattr(sr, "_get_frontend_dir", lambda: Path("/nonexistent/directory"))
    response = client.get("/")
    assert response.status_code == 404


def test_serve_css_success(client):
    """Test GET /css/base.css serves stylesheet."""
    response = client.get("/css/base.css")
    assert response.status_code == 200
    assert b"PulseAuth Design System" in response.data


def test_serve_css_not_found(client):
    """Test GET /css/missing.css returns 404."""
    response = client.get("/css/missing.css")
    assert response.status_code == 404


def test_serve_js_success(client):
    """Test GET /js/app.js serves JavaScript module."""
    response = client.get("/js/app.js")
    assert response.status_code == 200
    assert b"initPlayground" in response.data


def test_serve_js_not_found(client):
    """Test GET /js/missing.js returns 404."""
    response = client.get("/js/missing.js")
    assert response.status_code == 404


def test_serve_public_file(client, tmp_path, monkeypatch):
    """Test GET /public/<filename> serves assets or 404."""
    test_frontend = tmp_path / "frontend"
    test_public = test_frontend / "public"
    test_public.mkdir(parents=True)
    (test_public / "robots.txt").write_text("User-agent: *")

    monkeypatch.setattr(sr, "_get_frontend_dir", lambda: test_frontend)

    res_ok = client.get("/public/robots.txt")
    assert res_ok.status_code == 200
    assert b"User-agent" in res_ok.data

    res_missing = client.get("/public/nonexistent.txt")
    assert res_missing.status_code == 404


def test_oauth_callback_success(client):
    """Test GET /callback renders authorization code received page."""
    response = client.get("/callback?code=test_code_123&state=test_state_abc")
    assert response.status_code == 200
    assert b"Authorization Response Received" in response.data
    assert b"test_code_123" in response.data
    assert b"test_state_abc" in response.data


def test_oauth_callback_error(client):
    """Test GET /callback renders error message when error parameter is present."""
    response = client.get(
        "/callback?error=access_denied&error_description=User+denied+access"
    )
    assert response.status_code == 200
    assert b"Error:" in response.data
    assert b"access_denied" in response.data
    assert b"User denied access" in response.data
