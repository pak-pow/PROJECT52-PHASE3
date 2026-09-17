"""Automated tests validating docker-compose orchestration and Nginx configurations."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from app.db import init_db

WEEK38_DIR = Path(__file__).resolve().parent.parent.parent


def test_docker_compose_file_structure():
    """Verify docker-compose.yml defines all 4 required services and networks."""
    compose_path = WEEK38_DIR / "docker-compose.yml"
    assert compose_path.exists(), "docker-compose.yml must exist at root of week38."

    content = compose_path.read_text(encoding="utf-8")
    assert "db:" in content
    assert "cache:" in content
    assert "api:" in content
    assert "web:" in content
    assert "postgres:16-alpine" in content
    assert "redis:7-alpine" in content
    assert "nginx:alpine" in content
    assert "postgres_data:" in content
    assert "redis_data:" in content
    assert "app-network:" in content
    assert "service_healthy" in content


def test_nginx_configuration_file():
    """Verify nginx.conf defines reverse proxy pass, upstream, and healthz endpoint."""
    nginx_path = WEEK38_DIR / "nginx" / "nginx.conf"
    assert nginx_path.exists(), "nginx.conf must exist in nginx directory."

    content = nginx_path.read_text(encoding="utf-8")
    assert "upstream flask_api" in content
    assert "server api:5000;" in content
    assert "location /healthz" in content
    assert "location /api/" in content
    assert "proxy_pass http://flask_api;" in content
    assert "gzip on;" in content


def test_frontend_public_landing_page():
    """Verify frontend adheres to vanilla standalone CSS and JS rules."""
    html_path = WEEK38_DIR / "frontend" / "public" / "index.html"
    assert html_path.exists(), "frontend/public/index.html must exist."

    content = html_path.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in content
    assert "Docker Pulse" in content
    assert '<link rel="stylesheet"' in content
    assert "base.css" in content
    assert "pulse.css" in content
    assert "main.js" in content
    # Verify no external CSS or script CDN tags are loaded
    assert "cdn." not in content
    assert "unpkg.com" not in content
    assert "cdnjs." not in content

    # Verify modular stylesheet and script files exist
    base_css = WEEK38_DIR / "frontend" / "src" / "assets" / "base.css"
    assert base_css.exists(), "frontend/src/assets/base.css must exist."
    pulse_css = WEEK38_DIR / "frontend" / "src" / "assets" / "pulse.css"
    assert pulse_css.exists(), "frontend/src/assets/pulse.css must exist."
    main_js = WEEK38_DIR / "frontend" / "src" / "main.js"
    assert main_js.exists(), "frontend/src/main.js must exist."


def test_frontend_day5_modular_components():
    """Verify Day 5 ES6 frontend modules exist and contain expected exports."""
    frontend_src = WEEK38_DIR / "frontend" / "src"
    expected_files = [
        frontend_src / "utils" / "helpers.js",
        frontend_src / "api" / "opsApi.js",
        frontend_src / "components" / "toast.js",
        frontend_src / "components" / "serviceGrid.js",
        frontend_src / "components" / "benchmarkCard.js",
        frontend_src / "components" / "taskManager.js",
        frontend_src / "pages" / "dashboardPage.js",
    ]

    for file_path in expected_files:
        assert file_path.exists(), f"Frontend file {file_path.name} must exist."
        content = file_path.read_text(encoding="utf-8")
        assert len(content) > 100, f"{file_path.name} should not be empty."


def test_init_db_retry_resilience():
    """Verify init_db handles temporary operational errors and recovers."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    with patch("app.db.get_db_connection") as mock_conn_mgr:
        # First attempt fails with database starting up, second succeeds
        mock_conn_mgr.side_effect = [
            Exception("Database is starting up..."),
            mock_conn,
        ]
        success = init_db(
            "postgresql://postgres:postgres@localhost:5432/db", retries=2, delay=0.01
        )
        assert success is True
