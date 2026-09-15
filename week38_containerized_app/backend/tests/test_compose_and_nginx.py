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
    """Verify frontend/public/index.html adheres to standalone CSS rules."""
    html_path = WEEK38_DIR / "frontend" / "public" / "index.html"
    assert html_path.exists(), "frontend/public/index.html must exist."

    content = html_path.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in content
    assert "Docker Pulse" in content
    assert "<style>" in content
    # Verify no external CSS or script CDN tags are loaded
    assert "cdn." not in content
    assert "unpkg.com" not in content
    assert "cdnjs." not in content


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
