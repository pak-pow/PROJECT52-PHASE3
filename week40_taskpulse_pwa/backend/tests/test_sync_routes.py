def test_batch_sync_create_and_update(client):
    """Verify offline CREATE and UPDATE mutations are applied."""
    mutations = [
        {
            "action": "CREATE",
            "entity_id": "offline_task_1",
            "payload": {
                "title": "Offline Created Task",
                "category": "work",
                "priority": "high",
            },
            "timestamp": "2026-09-30T10:00:00.000Z",
        },
        {
            "action": "UPDATE",
            "entity_id": "offline_task_1",
            "payload": {
                "title": "Offline Created Task (Edited)",
                "completed": True,
            },
            "timestamp": "2026-09-30T10:05:00.000Z",
        },
    ]

    res = client.post("/api/sync/batch", json={"mutations": mutations})
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    assert data["processed"] == 2
    assert data["conflicts"] == 0

    # Verify task in DB
    get_res = client.get("/api/tasks/offline_task_1")
    assert get_res.status_code == 200
    task = get_res.get_json()["data"]
    assert task["title"] == "Offline Created Task (Edited)"
    assert task["completed"] is True


def test_batch_sync_toggle_and_delete(client):
    """Verify offline TOGGLE and DELETE mutations."""
    # Pre-create task
    client.post(
        "/api/tasks",
        json={"id": "sync_target_1", "title": "Target for delete"},
    )

    mutations = [
        {
            "action": "TOGGLE",
            "entity_id": "sync_target_1",
            "payload": {"completed": True},
            "timestamp": "2026-09-30T12:00:00.000Z",
        },
        {
            "action": "DELETE",
            "entity_id": "sync_target_1",
            "timestamp": "2026-09-30T12:01:00.000Z",
        },
    ]

    res = client.post("/api/sync/batch", json={"mutations": mutations})
    assert res.status_code == 200
    data = res.get_json()
    assert data["processed"] == 2

    # Task should be soft-deleted and not appear in active tasks
    active_res = client.get("/api/tasks")
    active_ids = [t["id"] for t in active_res.get_json()["data"]]
    assert "sync_target_1" not in active_ids


def test_batch_sync_lww_conflict_resolution(client):
    """Verify Last-Write-Wins: older client mutation is rejected."""
    # Create task with newer server timestamp
    client.post(
        "/api/tasks",
        json={
            "id": "conflict_task_1",
            "title": "Server Newer Version",
            "updated_at": "2026-09-30T15:00:00.000Z",
        },
    )

    # Attempt to sync an older client mutation
    stale_mutations = [
        {
            "action": "UPDATE",
            "entity_id": "conflict_task_1",
            "payload": {"title": "Stale Client Version"},
            "timestamp": "2026-09-30T14:00:00.000Z",
        }
    ]

    res = client.post("/api/sync/batch", json={"mutations": stale_mutations})
    assert res.status_code == 200
    data = res.get_json()
    assert data["conflicts"] == 1
    assert data["processed"] == 0

    # Task title should remain server version
    task_res = client.get("/api/tasks/conflict_task_1")
    assert task_res.get_json()["data"]["title"] == "Server Newer Version"


def test_batch_sync_invalid_input(client):
    """Verify error handling for invalid mutation payloads."""
    # Not a list
    res = client.post("/api/sync/batch", json={"mutations": "not-a-list"})
    assert res.status_code == 400
    assert "must be an array" in res.get_json()["message"]

    # Exceeding batch size
    too_many = [
        {"action": "CREATE", "entity_id": f"id_{i}"} for i in range(105)
    ]
    res_large = client.post("/api/sync/batch", json={"mutations": too_many})
    assert res_large.status_code == 400
    assert "exceeds maximum limit" in res_large.get_json()["message"]


def test_sync_delta(client):
    """Verify delta endpoint returns items created/updated after timestamp."""
    client.post(
        "/api/tasks",
        json={
            "id": "delta_old",
            "title": "Old Task",
            "updated_at": "2026-09-30T08:00:00.000Z",
        },
    )
    client.post(
        "/api/tasks",
        json={
            "id": "delta_new",
            "title": "New Task",
            "updated_at": "2026-09-30T10:00:00.000Z",
        },
    )

    # Query delta since 09:00:00
    res = client.get("/api/sync/delta?since=2026-09-30T09:00:00.000Z")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    assert data["count"] == 1
    assert data["delta"][0]["id"] == "delta_new"
