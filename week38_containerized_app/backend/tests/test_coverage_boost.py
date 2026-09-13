"""Tests targeting branch coverage across DB, Cache, and Model edge cases."""

import os
from unittest.mock import MagicMock, patch

import pytest

from app import create_app
from app.cache import CacheClient
from app.config.settings import (
    DevelopmentConfig,
    ProductionConfig,
    TestingConfig,
    _get_git_commit,
    get_config,
)
from app.db import check_db_health, execute_query, get_db_connection, init_db
from app.models.task_model import TaskModel


def test_config_resolution():
    """Verify resolution of all environment config classes."""
    assert get_config("development") == DevelopmentConfig
    assert get_config("testing") == TestingConfig
    assert get_config("production") == ProductionConfig
    assert get_config("unknown_env") == DevelopmentConfig


def test_git_commit_env_override():
    """Verify _get_git_commit uses GIT_COMMIT_SHA when set."""
    with patch.dict(os.environ, {"GIT_COMMIT_SHA": "abcdef123456"}):
        assert _get_git_commit() == "abcdef1"

    with patch("subprocess.check_output", side_effect=Exception("No git")):
        with patch.dict(os.environ, {}, clear=True):
            assert _get_git_commit() == "unknown"


def test_app_factory_error_handling():
    """Verify app factory handles 500 error handler and db init failure."""
    app = create_app("testing", init_database=False)
    app.config["TESTING"] = False
    app.config["PROPAGATE_EXCEPTIONS"] = False
    app.config["DEBUG"] = False

    @app.route("/api/v1/simulate_error")
    def simulate_error():
        raise RuntimeError("Intentional Test Crash")

    client = app.test_client()
    res = client.get("/api/v1/simulate_error")
    assert res.status_code == 500
    assert res.get_json()["error"] == "Internal server error."

    # Test init_db failure branch in factory
    with patch("app.init_db", side_effect=Exception("Database lock")):
        failing_app = create_app("testing", init_database=True)
        assert failing_app is not None


def test_redis_cache_branch_coverage():
    """Verify CacheClient interactions when Redis client is active."""
    mock_redis = MagicMock()
    mock_redis.ping.return_value = True
    mock_redis.get.return_value = "redis_value"
    mock_redis.set.return_value = True
    mock_redis.setex.return_value = True
    mock_redis.delete.return_value = 1
    mock_redis.flushdb.return_value = True
    mock_redis.info.return_value = {"keyspace_hits": 42, "keyspace_misses": 5}

    with patch("redis.from_url", return_value=mock_redis):
        client = CacheClient(redis_url="redis://localhost:6379/0")
        assert client.engine == "redis"
        assert client.get("key") == "redis_value"
        assert client.set("key", "val") is True
        assert client.set("key", "val", ttl=30) is True
        assert client.delete("key") is True
        assert client.clear() is True
        assert client.check_health()["status"] == "healthy"
        stats = client.get_stats()
        assert stats["hits"] == 42
        assert stats["misses"] == 5

        # Test Redis exception fallback to in-memory
        mock_redis.get.side_effect = Exception("Redis connection lost")
        mock_redis.set.side_effect = Exception("Redis write failed")
        mock_redis.delete.side_effect = Exception("Redis del failed")
        mock_redis.flushdb.side_effect = Exception("Redis flush failed")
        mock_redis.ping.side_effect = Exception("Ping failed")

        assert client.get("fallback_key") is None
        assert client.set("fallback_key", "val") is True
        assert client.delete("fallback_key") is True
        assert client.clear() is True
        assert client.check_health()["status"] == "unhealthy"


def test_postgres_db_branch_coverage():
    """Verify execute_query and init_db under postgresql URL configuration."""
    pg_url = "postgresql://postgres:postgres@localhost:5432/testdb"
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.fetchall.return_value = [{"id": 1, "title": "PG Task"}]

    with patch("psycopg2.connect", return_value=mock_conn):
        # 1. Connection manager
        with get_db_connection(pg_url) as conn:
            assert conn is not None

        # 2. execute_query with placeholder translation ? -> %s
        res = execute_query(
            "SELECT * FROM tasks WHERE id = ?;", (1,), db_url=pg_url, fetch_all=True
        )
        assert len(res) == 1
        # Verify query had %s placeholder
        args, _ = mock_cursor.execute.call_args
        assert "%s" in args[0]

        # 3. init_db on PostgreSQL
        success = init_db(pg_url)
        assert success is True

    # 4. Missing schema file handling
    with patch("pathlib.Path.exists", return_value=False):
        with pytest.raises(FileNotFoundError):
            init_db("sqlite:///:memory:")

    # 5. check_db_health with None URL
    health_none = check_db_health(None)
    assert health_none is not None

    # 6. execute_query with commit returning rowcount
    with patch("app.db.get_db_connection") as mock_conn_mgr:
        m_conn = MagicMock()
        m_cur = MagicMock()
        del m_cur.lastrowid
        m_cur.rowcount = 3
        m_conn.cursor.return_value = m_cur
        mock_conn_mgr.return_value.__enter__.return_value = m_conn
        rc = execute_query("UPDATE tasks SET status = ?;", ("completed",), commit=True)
        assert rc == 3


def test_task_model_edge_cases(app):
    """Verify task model filtering, update edge cases, and empty updates."""
    db_url = app.config["DATABASE_URL"]

    # Filtered get_all
    t1 = TaskModel.create(
        "Filter Prio", priority="critical", status="pending", db_url=db_url
    )
    t2 = TaskModel.create(
        "Filter Status", priority="low", status="completed", db_url=db_url
    )

    filtered_prio = TaskModel.get_all(priority="critical", db_url=db_url)
    assert any(t["id"] == t1["id"] for t in filtered_prio)

    filtered_status = TaskModel.get_all(status="completed", db_url=db_url)
    assert any(t["id"] == t2["id"] for t in filtered_status)

    # Update edge cases
    with pytest.raises(ValueError, match="cannot be empty"):
        TaskModel.update(t1["id"], title="   ", db_url=db_url)

    with pytest.raises(ValueError, match="cannot exceed 255"):
        TaskModel.update(t1["id"], title="x" * 256, db_url=db_url)

    with pytest.raises(ValueError, match="Invalid status"):
        TaskModel.update(t1["id"], status="non_existent", db_url=db_url)

    # Empty update (no fields changed)
    same = TaskModel.update(t1["id"], db_url=db_url)
    assert same["id"] == t1["id"]

    # Update description only
    with_desc = TaskModel.update(t1["id"], description="Added details", db_url=db_url)
    assert with_desc["description"] == "Added details"


def test_task_routes_caching_branches(client):
    """Verify cached hit branches in list_tasks and tasks_summary routes."""
    client.post("/api/v1/tasks", json={"title": "Task For Cache"})

    # 1. list_tasks cache HIT
    r1 = client.get("/api/v1/tasks")
    assert r1.status_code == 200
    assert r1.headers.get("X-Cache") == "MISS"

    r2 = client.get("/api/v1/tasks")
    assert r2.status_code == 200
    assert r2.headers.get("X-Cache") == "HIT"
    assert r2.get_json()["cached"] is True

    # 2. tasks_summary cache HIT
    s1 = client.get("/api/v1/tasks/summary")
    assert s1.status_code == 200
    assert s1.get_json()["cached"] is False

    s2 = client.get("/api/v1/tasks/summary")
    assert s2.status_code == 200
    assert s2.get_json()["cached"] is True
