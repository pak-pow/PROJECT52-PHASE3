"""Unit tests for database and cache edge cases and error handlers."""

import time
from unittest.mock import patch

from app.cache import InMemoryCache, cache
from app.db import check_db_health, is_postgres
from app.models.task_model import TaskModel


def test_is_postgres_detection():
    """Verify detection of postgresql URL schemes."""
    assert is_postgres("postgresql://user:pass@host:5432/db") is True
    assert is_postgres("postgres://user:pass@host:5432/db") is True
    assert is_postgres("sqlite:///tasks.db") is False
    assert is_postgres("sqlite:///:memory:") is False


def test_in_memory_cache_ttl_and_stats():
    """Verify in-memory cache TTL expiration and telemetry counters."""
    mem_cache = InMemoryCache()
    mem_cache.set("short_lived", "value", ttl=1)
    assert mem_cache.get("short_lived") == "value"
    assert mem_cache.hits == 1

    # Sleep to expire
    time.sleep(1.05)
    assert mem_cache.get("short_lived") is None
    assert mem_cache.misses == 1

    # Test delete
    mem_cache.set("del_key", "del_val")
    assert mem_cache.delete("del_key") is True
    assert mem_cache.delete("non_existent") is False

    # Test clear
    mem_cache.set("k1", "v1")
    mem_cache.clear()
    assert mem_cache.size() == 0


def test_cache_stats_method():
    """Verify cache.get_stats returns engine and metrics."""
    stats = cache.get_stats()
    assert "engine" in stats
    assert "hits" in stats
    assert "misses" in stats


def test_db_health_failure_handling():
    """Verify check_db_health returns unhealthy dictionary on exception."""
    with patch("app.db.get_db_connection") as mock_conn:
        mock_conn.side_effect = Exception("Simulated disk error")
        result = check_db_health("sqlite:///nonexistent/invalid.db")
        assert result["status"] == "unhealthy"
        assert "Simulated disk error" in result["error"]


def test_task_model_record_metric(app):
    """Verify operational metric recording in database."""
    metric_id = TaskModel.record_metric(
        "container_cpu_usage", 42.5, details="core_0", db_url=app.config["DATABASE_URL"]
    )
    assert metric_id is not None


def test_custom_404_handler(client):
    """Verify custom 404 JSON error handler."""
    response = client.get("/api/v1/nonexistent_route")
    assert response.status_code == 404
    assert response.get_json()["error"] == "Resource not found."
