def test_list_deployments_empty(client):
    """Verify listing deployments returns empty list initially."""
    res = client.get("/api/v1/deployments")
    assert res.status_code == 200
    data = res.get_json()
    assert "deployments" in data
    assert "count" in data


def test_record_deployment_success(client):
    """Verify recording a valid deployment returns 201 Created."""
    payload = {
        "service_name": "payment-service",
        "environment": "staging",
        "version": "1.2.0",
        "commit_hash": "a1b2c3d4e5f6",
        "triggered_by": "github-actions",
        "status": "success",
        "notes": "Automated deployment via CI/CD",
    }
    res = client.post("/api/v1/deployments", json=payload)
    assert res.status_code == 201
    data = res.get_json()
    assert data["message"] == "Deployment recorded successfully."
    assert data["deployment"]["environment"] == "staging"
    assert data["deployment"]["version"] == "1.2.0"
    assert data["deployment"]["commit_hash"] == "a1b2c3d4e5f6"


def test_record_deployment_missing_fields(client):
    """Verify recording a deployment with missing fields returns 400."""
    res = client.post(
        "/api/v1/deployments",
        json={"service_name": "payment-service"},
    )
    assert res.status_code == 400
    assert "required" in res.get_json()["error"].lower()


def test_record_deployment_invalid_environment(client):
    """Verify invalid environment string returns 400."""
    res = client.post(
        "/api/v1/deployments",
        json={
            "environment": "invalid_env_name",
            "version": "1.0.0",
            "commit_hash": "abc123",
        },
    )
    assert res.status_code == 400
    assert "invalid environment" in res.get_json()["error"].lower()


def test_list_deployments_filter_by_environment(client):
    """Verify filtering deployments by environment."""
    client.post(
        "/api/v1/deployments",
        json={
            "environment": "production",
            "version": "1.0.0",
            "commit_hash": "prod-hash",
        },
    )
    res = client.get("/api/v1/deployments?environment=production")
    assert res.status_code == 200
    data = res.get_json()
    assert data["environment_filter"] == "production"
    assert all(d["environment"] == "production" for d in data["deployments"])


def test_record_and_list_pipeline_runs(client):
    """Verify recording and querying pipeline run history."""
    run_payload = {
        "workflow_name": "ci.yml",
        "branch": "main",
        "commit_sha": "f1e2d3c4",
        "lint_status": "passed",
        "security_status": "passed",
        "test_status": "passed",
        "build_status": "passed",
        "deploy_status": "passed",
        "overall_status": "success",
        "duration_seconds": 45.2,
    }
    post_res = client.post("/api/v1/pipeline-runs", json=run_payload)
    assert post_res.status_code == 201
    run_data = post_res.get_json()
    assert run_data["run"]["workflow_name"] == "ci.yml"
    assert run_data["run"]["overall_status"] == "success"

    get_res = client.get("/api/v1/pipeline-runs")
    assert get_res.status_code == 200
    assert get_res.get_json()["count"] >= 1
