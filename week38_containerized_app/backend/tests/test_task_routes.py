"""Unit tests for task CRUD, Redis/in-memory caching, and benchmarks."""


def test_list_tasks_empty(client):
    """Verify listing tasks when none exist returns empty list and cache miss."""
    response = client.get("/api/v1/tasks")
    assert response.status_code == 200
    data = response.get_json()
    assert data["tasks"] == []
    assert data["count"] == 0
    assert response.headers.get("X-Cache") == "MISS"


def test_create_task_success(client):
    """Verify task creation returns 201 and persists to database."""
    payload = {
        "title": "Deploy PostgreSQL Container",
        "description": "Configure named volume and port mapping",
        "priority": "high",
        "status": "in_progress",
    }
    response = client.post("/api/v1/tasks", json=payload)
    assert response.status_code == 201
    data = response.get_json()
    assert data["task"]["title"] == payload["title"]
    assert data["task"]["priority"] == "high"
    assert data["task"]["status"] == "in_progress"
    assert "id" in data["task"]


def test_create_task_validation_errors(client):
    """Verify validation on empty title, invalid priority, and status."""
    # Empty title
    res = client.post("/api/v1/tasks", json={"title": "   "})
    assert res.status_code == 400
    assert "cannot be empty" in res.get_json()["error"]

    # Title exceeds 255 chars
    res = client.post("/api/v1/tasks", json={"title": "x" * 256})
    assert res.status_code == 400
    assert "cannot exceed 255" in res.get_json()["error"]

    # Invalid priority
    res = client.post(
        "/api/v1/tasks", json={"title": "Valid Title", "priority": "super_urgent"}
    )
    assert res.status_code == 400
    assert "Invalid priority" in res.get_json()["error"]

    # Invalid status
    res = client.post(
        "/api/v1/tasks", json={"title": "Valid Title", "status": "destroyed"}
    )
    assert res.status_code == 400
    assert "Invalid status" in res.get_json()["error"]


def test_get_and_cache_task(client):
    """Verify task retrieval by ID and cache hit on second fetch."""
    # Create task
    res_create = client.post("/api/v1/tasks", json={"title": "Cache Probe Task"})
    task_id = res_create.get_json()["task"]["id"]

    # First fetch (cache miss)
    res1 = client.get(f"/api/v1/tasks/{task_id}")
    assert res1.status_code == 200
    assert res1.get_json()["cached"] is False

    # Second fetch (cache hit)
    res2 = client.get(f"/api/v1/tasks/{task_id}")
    assert res2.status_code == 200
    assert res2.get_json()["cached"] is True


def test_get_task_not_found(client):
    """Verify 404 when querying non-existent task."""
    response = client.get("/api/v1/tasks/999999")
    assert response.status_code == 404
    assert response.get_json()["error"] == "Task not found."


def test_update_task(client):
    """Verify updating task priority and status."""
    res_create = client.post(
        "/api/v1/tasks", json={"title": "Original Title", "priority": "low"}
    )
    task_id = res_create.get_json()["task"]["id"]

    # Valid update
    res_update = client.put(
        f"/api/v1/tasks/{task_id}",
        json={"title": "Updated Title", "priority": "critical", "status": "completed"},
    )
    assert res_update.status_code == 200
    updated_data = res_update.get_json()["task"]
    assert updated_data["title"] == "Updated Title"
    assert updated_data["priority"] == "critical"
    assert updated_data["status"] == "completed"

    # Update non-existent task
    res_404 = client.put("/api/v1/tasks/999999", json={"title": "Ghost Task"})
    assert res_404.status_code == 404

    # Update with invalid priority
    res_invalid = client.put(
        f"/api/v1/tasks/{task_id}", json={"priority": "invalid_prio"}
    )
    assert res_invalid.status_code == 400


def test_delete_task(client):
    """Verify task deletion and subsequent 404."""
    res_create = client.post("/api/v1/tasks", json={"title": "Task to Delete"})
    task_id = res_create.get_json()["task"]["id"]

    # Delete
    res_del = client.delete(f"/api/v1/tasks/{task_id}")
    assert res_del.status_code == 200
    assert "deleted successfully" in res_del.get_json()["message"]

    # Subsequent delete returns 404
    res_del2 = client.delete(f"/api/v1/tasks/{task_id}")
    assert res_del2.status_code == 404


def test_task_summary_metrics(client):
    """Verify summary endpoint aggregates counts by status and priority."""
    client.post(
        "/api/v1/tasks",
        json={"title": "Task 1", "priority": "critical", "status": "pending"},
    )
    client.post(
        "/api/v1/tasks",
        json={"title": "Task 2", "priority": "low", "status": "completed"},
    )

    response = client.get("/api/v1/tasks/summary")
    assert response.status_code == 200
    summary = response.get_json()["summary"]
    assert summary["total_tasks"] >= 2
    assert summary["by_priority"]["critical"] >= 1
    assert summary["by_status"]["completed"] >= 1


def test_benchmark_endpoint(client):
    """Verify /api/v1/benchmark executes both DB and cache latency checks."""
    response = client.get("/api/v1/benchmark")
    assert response.status_code == 200
    data = response.get_json()
    assert "database" in data
    assert "cache" in data
    assert "latency_ms" in data["database"]
    assert "latency_ms" in data["cache"]
    assert "speedup_factor" in data
