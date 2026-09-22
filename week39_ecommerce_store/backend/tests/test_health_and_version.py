def test_health_check(client):
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "healthy"
    assert data["service"] == "shoppulse-backend"
    assert "timestamp" in data
    assert "environment" in data


def test_version_check(client):
    res = client.get("/api/v1/version")
    assert res.status_code == 200
    data = res.get_json()
    assert data["version"] == "1.0.0"
    assert data["service"] == "shoppulse-backend"
    assert "git_commit" in data


def test_ready_check_success(client):
    res = client.get("/api/v1/ready")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "ready"
    assert data["database"] == "connected"
    assert "latency_ms" in data


def test_ready_check_failure(client, monkeypatch):
    import app.routes.health_routes as hr

    monkeypatch.setattr(hr, "ping_db", lambda: (False, 150.0))

    res = client.get("/api/v1/ready")
    assert res.status_code == 503
    data = res.get_json()
    assert data["status"] == "unready"
    assert data["database"] == "disconnected"
