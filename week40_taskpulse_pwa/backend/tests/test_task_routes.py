def test_create_task_success(client):
    """Verify creating a task returns 201 with saved payload."""
    payload = {
        "title": "Build Service Worker",
        "description": "Configure precaching and network routing.",
        "category": "work",
        "priority": "high",
    }
    response = client.post("/api/tasks", json=payload)
    assert response.status_code == 201
    data = response.get_json()
    assert data["status"] == "success"
    task = data["data"]
    assert task["title"] == "Build Service Worker"
    assert task["category"] == "work"
    assert task["completed"] is False
    assert task["is_deleted"] is False
    assert "id" in task


def test_create_task_validation_error(client):
    """Verify creating task with empty title returns 400 error."""
    response = client.post("/api/tasks", json={"title": "   "})
    assert response.status_code == 400
    data = response.get_json()
    assert data["status"] == "error"
    assert "title is required" in data["message"]


def test_get_tasks_and_category_filter(client):
    """Verify task listing and category filtering."""
    client.post(
        "/api/tasks",
        json={"title": "Work item 1", "category": "work"},
    )
    client.post(
        "/api/tasks",
        json={"title": "Personal item 1", "category": "personal"},
    )
    client.post(
        "/api/tasks",
        json={"title": "Urgent item 1", "category": "urgent"},
    )

    # All tasks
    res_all = client.get("/api/tasks")
    assert res_all.status_code == 200
    data_all = res_all.get_json()
    assert data_all["count"] == 3

    # Filter work
    res_work = client.get("/api/tasks?category=work")
    assert res_work.status_code == 200
    data_work = res_work.get_json()
    assert data_work["count"] == 1
    assert data_work["data"][0]["title"] == "Work item 1"

    # Filter personal
    res_pers = client.get("/api/tasks?category=personal")
    assert res_pers.status_code == 200
    data_pers = res_pers.get_json()
    assert data_pers["count"] == 1
    assert data_pers["data"][0]["title"] == "Personal item 1"


def test_get_task_by_id_and_not_found(client):
    """Verify retrieving specific task by ID and 404 for unknown task."""
    create_res = client.post(
        "/api/tasks", json={"title": "Inspect single task"}
    )
    task_id = create_res.get_json()["data"]["id"]

    res = client.get(f"/api/tasks/{task_id}")
    assert res.status_code == 200
    assert res.get_json()["data"]["title"] == "Inspect single task"

    res_404 = client.get("/api/tasks/unknown_id_123")
    assert res_404.status_code == 404
    assert res_404.get_json()["status"] == "error"


def test_update_task(client):
    """Verify updating title, completion status, and category."""
    create_res = client.post(
        "/api/tasks", json={"title": "Initial Title", "completed": False}
    )
    task_id = create_res.get_json()["data"]["id"]

    update_payload = {
        "title": "Updated Title",
        "completed": True,
        "category": "urgent",
    }
    update_res = client.put(f"/api/tasks/{task_id}", json=update_payload)
    assert update_res.status_code == 200
    updated_task = update_res.get_json()["data"]
    assert updated_task["title"] == "Updated Title"
    assert updated_task["completed"] is True
    assert updated_task["category"] == "urgent"

    # Update non-existent task
    res_404 = client.put("/api/tasks/non_existent_99", json={"title": "Test"})
    assert res_404.status_code == 404


def test_delete_task(client):
    """Verify soft-deleting a task removes it from regular listing."""
    create_res = client.post("/api/tasks", json={"title": "To be deleted"})
    task_id = create_res.get_json()["data"]["id"]

    del_res = client.delete(f"/api/tasks/{task_id}")
    assert del_res.status_code == 200
    assert del_res.get_json()["status"] == "success"

    # Verify task is no longer in active listing
    list_res = client.get("/api/tasks")
    ids = [t["id"] for t in list_res.get_json()["data"]]
    assert task_id not in ids

    # Delete non-existent task returns 404
    del_404 = client.delete("/api/tasks/unknown_task_delete")
    assert del_404.status_code == 404
