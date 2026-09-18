"""Resilience, security, and edge-case unit tests.

Validates application behavior under simulated database outages, cache dropouts,
input tampering, SQL injection/XSS attempts, and verifies Nginx security settings.
"""

import json
from pathlib import Path
from unittest.mock import patch


def test_nginx_security_headers_and_rate_limits():
    """Verify Nginx reverse proxy configuration enforces security directives."""
    nginx_conf_path = (
        Path(__file__).resolve().parent.parent.parent / "nginx" / "nginx.conf"
    )
    assert nginx_conf_path.exists(), "nginx.conf must exist in nginx directory"

    content = nginx_conf_path.read_text(encoding="utf-8")
    # Security response headers
    assert "X-Frame-Options" in content
    assert "X-Content-Type-Options" in content
    assert "X-XSS-Protection" in content
    assert "Referrer-Policy" in content

    # Payload limits and rate limiting
    assert "client_max_body_size 1M;" in content
    assert "limit_req_zone" in content
    assert "limit_req zone=api_limit" in content


def test_create_task_content_type_validation(client):
    """Verify non-JSON and malformed payloads are rejected."""
    # 1. Non-JSON Content-Type
    res1 = client.post(
        "/api/v1/tasks",
        data="plain text body",
        content_type="text/plain",
    )
    assert res1.status_code == 415
    assert "application/json" in res1.get_json()["error"]

    # 2. Non-dict JSON payload (JSON array)
    res2 = client.post(
        "/api/v1/tasks",
        data=json.dumps([1, 2, 3]),
        content_type="application/json",
    )
    assert res2.status_code == 400
    assert "JSON object" in res2.get_json()["error"]

    # 3. Empty body defaults to empty dict and triggers validation error
    res3 = client.post(
        "/api/v1/tasks",
        data="",
        content_type="application/json",
    )
    assert res3.status_code == 400


def test_create_task_field_type_and_bounds_validation(client):
    """Verify type safety and string length bounds on task creation."""
    # 1. Numeric title
    res1 = client.post(
        "/api/v1/tasks",
        json={"title": 9999},
    )
    assert res1.status_code == 400
    assert "must be a string" in res1.get_json()["error"]

    # 2. List description
    res2 = client.post(
        "/api/v1/tasks",
        json={"title": "Valid Title", "description": ["item1", "item2"]},
    )
    assert res2.status_code == 400
    assert "must be a string" in res2.get_json()["error"]

    # 3. Oversized title > 255 chars
    res3 = client.post(
        "/api/v1/tasks",
        json={"title": "A" * 256},
    )
    assert res3.status_code == 400
    assert "cannot exceed 255" in res3.get_json()["error"]

    # 4. Invalid priority
    res4 = client.post(
        "/api/v1/tasks",
        json={"title": "Valid Title", "priority": "ultra_mega_urgent"},
    )
    assert res4.status_code == 400
    assert "Invalid priority" in res4.get_json()["error"]


def test_update_task_validation(client):
    """Verify input validation on task update endpoint."""
    # Create valid task first
    create_res = client.post(
        "/api/v1/tasks",
        json={"title": "Target Task", "priority": "low"},
    )
    assert create_res.status_code == 201
    task_id = create_res.get_json()["task"]["id"]

    # 1. Non-JSON Content-Type
    res1 = client.put(
        f"/api/v1/tasks/{task_id}",
        data="raw string",
        content_type="text/plain",
    )
    assert res1.status_code == 415

    # 2. Non-dict JSON payload
    res2 = client.put(
        f"/api/v1/tasks/{task_id}",
        data=json.dumps("simple string"),
        content_type="application/json",
    )
    assert res2.status_code == 400

    # 3. Numeric title
    res3 = client.put(
        f"/api/v1/tasks/{task_id}",
        json={"title": 42},
    )
    assert res3.status_code == 400

    # 4. Non-string description
    res4 = client.put(
        f"/api/v1/tasks/{task_id}",
        json={"description": 12345},
    )
    assert res4.status_code == 400

    # 5. Empty title update
    res5 = client.put(
        f"/api/v1/tasks/{task_id}",
        json={"title": "   "},
    )
    assert res5.status_code == 400

    # 6. Invalid status update
    res6 = client.put(
        f"/api/v1/tasks/{task_id}",
        json={"status": "invalid_status_value"},
    )
    assert res6.status_code == 400


def test_sql_injection_and_xss_input_safety(client):
    """Verify SQL injection and XSS payloads are handled safely as plain text."""
    xss_payload = "<script>alert('xss')</script><div>Injected HTML</div>"
    sql_payload = "'; DROP TABLE tasks; SELECT * FROM pg_user; --"

    res = client.post(
        "/api/v1/tasks",
        json={
            "title": xss_payload,
            "description": sql_payload,
            "priority": "high",
        },
    )
    assert res.status_code == 201
    task = res.get_json()["task"]
    task_id = task["id"]

    # Retrieve and verify exact string preservation without code execution
    fetch_res = client.get(f"/api/v1/tasks/{task_id}")
    assert fetch_res.status_code == 200
    fetched_task = fetch_res.get_json()["task"]

    assert fetched_task["title"] == xss_payload
    assert fetched_task["description"] == sql_payload

    # Verify tasks table is intact by listing all
    list_res = client.get("/api/v1/tasks")
    assert list_res.status_code == 200


def test_database_outage_graceful_503(client):
    """Verify database connection interruptions return HTTP 503 instead of crashing."""
    with patch(
        "app.models.task_model.TaskModel.get_all",
        side_effect=RuntimeError("Database connection lost"),
    ):
        res1 = client.get("/api/v1/tasks?no_cache=true")
        assert res1.status_code == 503
        assert "temporarily unavailable" in res1.get_json()["error"]

    with patch(
        "app.models.task_model.TaskModel.create",
        side_effect=RuntimeError("DB write timeout"),
    ):
        res2 = client.post(
            "/api/v1/tasks",
            json={"title": "Test Task"},
        )
        assert res2.status_code == 503
        assert "temporarily unavailable" in res2.get_json()["error"]

    with patch(
        "app.models.task_model.TaskModel.get_by_id",
        side_effect=RuntimeError("DB query error"),
    ):
        res3 = client.get("/api/v1/tasks/999")
        assert res3.status_code == 503
        assert "temporarily unavailable" in res3.get_json()["error"]

    with patch(
        "app.models.task_model.TaskModel.update",
        side_effect=RuntimeError("DB update failed"),
    ):
        res4 = client.put(
            "/api/v1/tasks/1",
            json={"title": "Updated"},
        )
        assert res4.status_code == 503
        assert "temporarily unavailable" in res4.get_json()["error"]

    with patch(
        "app.models.task_model.TaskModel.delete",
        side_effect=RuntimeError("DB delete failed"),
    ):
        res5 = client.delete("/api/v1/tasks/1")
        assert res5.status_code == 503
        assert "temporarily unavailable" in res5.get_json()["error"]

    with patch(
        "app.models.task_model.TaskModel.get_summary",
        side_effect=RuntimeError("DB aggregate failed"),
    ):
        res6 = client.get("/api/v1/tasks/summary")
        assert res6.status_code == 503
        assert "temporarily unavailable" in res6.get_json()["error"]


def test_cache_outage_tolerance(client):
    """Verify application functions uninterrupted when cache fails."""
    with patch("app.routes.task_routes.cache.get", side_effect=Exception("Redis down")):
        with patch(
            "app.routes.task_routes.cache.set", side_effect=Exception("Redis down")
        ):
            # List tasks continues through DB fallback
            res1 = client.get("/api/v1/tasks")
            assert res1.status_code == 200
            assert "tasks" in res1.get_json()

    with patch(
        "app.routes.task_routes.cache.delete", side_effect=Exception("Redis down")
    ):
        # Create task completes DB write despite cache invalidation error
        res2 = client.post(
            "/api/v1/tasks",
            json={"title": "Cache Outage Task", "priority": "medium"},
        )
        assert res2.status_code == 201
        assert res2.get_json()["task"]["title"] == "Cache Outage Task"


def test_readiness_probe_degraded_evaluation(client):
    """Verify /ready probe reports 200 when ready and 503 when degraded."""
    # 1. Healthy database and cache -> 200 ready
    with patch("app.routes.health_routes.check_db_health") as mock_db:
        with patch("app.routes.health_routes.cache.check_health") as mock_cache:
            mock_db.return_value = {"status": "healthy", "latency_ms": 1.5}
            mock_cache.return_value = {"status": "healthy", "latency_ms": 0.3}

            res = client.get("/api/v1/ready")
            assert res.status_code == 200
            data = res.get_json()
            assert data["status"] == "ready"

    # 2. Database down, cache healthy -> 503 degraded
    with patch("app.routes.health_routes.check_db_health") as mock_db:
        with patch("app.routes.health_routes.cache.check_health") as mock_cache:
            mock_db.return_value = {
                "status": "unhealthy",
                "error": "connection refused",
            }
            mock_cache.return_value = {"status": "healthy", "latency_ms": 0.3}

            res = client.get("/api/v1/ready")
            assert res.status_code == 503
            data = res.get_json()
            assert data["status"] == "degraded"
            assert data["database"]["status"] == "unhealthy"

    # 3. Database healthy, cache down -> 503 degraded
    with patch("app.routes.health_routes.check_db_health") as mock_db:
        with patch("app.routes.health_routes.cache.check_health") as mock_cache:
            mock_db.return_value = {"status": "healthy", "latency_ms": 1.2}
            mock_cache.return_value = {"status": "unhealthy", "error": "timeout"}

            res = client.get("/api/v1/ready")
            assert res.status_code == 503
            data = res.get_json()
            assert data["status"] == "degraded"
            assert data["cache"]["status"] == "unhealthy"
