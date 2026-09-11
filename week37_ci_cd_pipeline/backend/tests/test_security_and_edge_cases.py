"""
Project 52 - Week 37: CI/CD Pipeline Setup
Security Edge Cases & Test Suite Hardening (Day 6)
"""

import builtins
import urllib.error

from app.models.deployment_model import DeploymentModel, PipelineRunModel
from app.routes.deployment_routes import _pipeline_lock
from scripts.smoke_test import run_smoke_tests

# =====================================================================
# 1. Badge Security & Path Traversal Tests
# =====================================================================


def test_badge_path_traversal_prevention(client):
    """Verify that path traversal attempts on /api/v1/badges/<name> are rejected."""
    traversal_attempts = [
        "../../etc/passwd",
        "..%2F..%2Fetc%2Fpasswd",
        "....badges.svg",
        "..%5c..%5capp.svg",
        "nested/sub/build.svg",
        "build.svg/../../app.py",
    ]
    for attempt in traversal_attempts:
        res = client.get(f"/api/v1/badges/{attempt}")
        assert res.status_code in (400, 404), f"Failed to reject traversal: {attempt}"
        if res.status_code == 400:
            assert "error" in res.get_json()


def test_badge_invalid_extensions(client):
    """Verify that non-SVG badge files cannot be requested."""
    invalid_files = [
        "script.py",
        "secrets.json",
        "deployments.db",
        "build.png",
        "coverage.svg.bak",
        "build",
    ]
    for filename in invalid_files:
        res = client.get(f"/api/v1/badges/{filename}")
        assert res.status_code == 400
        assert "invalid badge filename" in res.get_json()["error"].lower()


def test_badge_not_found_returns_404(client):
    """Verify requesting a non-existent SVG returns 404."""
    res = client.get("/api/v1/badges/non_existent_badge_xyz.svg")
    assert res.status_code == 404
    data = res.get_json()
    assert "not found" in data["error"].lower()


def test_badge_read_io_error_handling(client, tmp_path, monkeypatch):
    """Verify handling when an existing badge file fails to read."""
    from app.routes import deployment_routes

    # Create dummy badge
    badge_dir = tmp_path / "badges"
    badge_dir.mkdir(exist_ok=True)
    badge_file = badge_dir / "test_io.svg"
    badge_file.write_text("<svg>test</svg>", encoding="utf-8")

    monkeypatch.setattr(deployment_routes, "BADGES_DIR", badge_dir)

    original_open = builtins.open

    def mock_open_failure(*args, **kwargs):
        if "test_io.svg" in str(args[0]):
            raise OSError("Simulated disk read error")
        return original_open(*args, **kwargs)

    monkeypatch.setattr(builtins, "open", mock_open_failure)

    res = client.get("/api/v1/badges/test_io.svg")
    assert res.status_code == 500
    assert "failed to read badge" in res.get_json()["error"].lower()


# =====================================================================
# 2. Pipeline Trigger Hardening & Concurrency Locking
# =====================================================================


def test_pipeline_trigger_invalid_stage(client):
    """Verify invalid pipeline stage strings are rejected with 400."""
    invalid_stages = ["hack_stage", "rm -rf /", "123", "deploy;reboot"]
    for stg in invalid_stages:
        res = client.post(
            "/api/v1/pipeline/trigger",
            json={"stage": stg, "environment": "staging"},
        )
        assert res.status_code == 400
        assert "invalid stage" in res.get_json()["error"].lower()


def test_pipeline_trigger_invalid_environment(client):
    """Verify invalid environment strings are rejected with 400."""
    invalid_envs = ["hack_env", "qa_testing", "sandbox", ""]
    for env in invalid_envs:
        res = client.post(
            "/api/v1/pipeline/trigger",
            json={"stage": "lint", "environment": env},
        )
        assert res.status_code == 400
        assert "invalid environment" in res.get_json()["error"].lower()


def test_pipeline_trigger_concurrency_conflict(client):
    """Verify concurrent pipeline triggers return 409 Conflict when lock is held."""
    acquired = _pipeline_lock.acquire(blocking=False)
    assert acquired is True, "Failed to acquire test lock"

    try:
        res = client.post(
            "/api/v1/pipeline/trigger",
            json={"stage": "lint", "environment": "staging"},
        )
        assert res.status_code == 409
        data = res.get_json()
        assert "already in progress" in data["error"].lower()
    finally:
        _pipeline_lock.release()


def test_pipeline_trigger_exception_releases_lock(client, monkeypatch):
    """Verify that if runner crashes, the concurrency lock is always released."""
    from scripts.pipeline_runner import PipelineRunner

    def crash_runner(self):
        raise RuntimeError("Simulated runner crash")

    monkeypatch.setattr(PipelineRunner, "run", crash_runner)

    res = client.post(
        "/api/v1/pipeline/trigger",
        json={"stage": "lint", "environment": "staging"},
    )
    assert res.status_code == 500
    assert "failed to execute pipeline" in res.get_json()["error"].lower()
    # Confirm lock is not held
    assert _pipeline_lock.locked() is False


# =====================================================================
# 3. Pipeline Report Edge Cases
# =====================================================================


def test_pipeline_report_missing_file(client, tmp_path, monkeypatch):
    """Verify 200 with empty stages is returned when pipeline_report.json is absent."""
    from app.routes import deployment_routes

    empty_reports = tmp_path / "empty_reports"
    empty_reports.mkdir(exist_ok=True)
    monkeypatch.setattr(deployment_routes, "REPORTS_DIR", empty_reports)

    res = client.get("/api/v1/pipeline-report")
    assert res.status_code == 200
    data = res.get_json()
    assert "message" in data
    assert data["stages"] == {}


def test_pipeline_report_corrupted_json(client, tmp_path, monkeypatch):
    """Verify 500 error handling when pipeline_report.json contains invalid JSON."""
    from app.routes import deployment_routes

    corrupt_dir = tmp_path / "corrupt_reports"
    corrupt_dir.mkdir(exist_ok=True)
    report_file = corrupt_dir / "pipeline_report.json"
    report_file.write_text(
        "{corrupt-json-data: true, missing_bracket", encoding="utf-8"
    )

    monkeypatch.setattr(deployment_routes, "REPORTS_DIR", corrupt_dir)

    res = client.get("/api/v1/pipeline-report")
    assert res.status_code == 500
    assert "failed to read pipeline report" in res.get_json()["error"].lower()


# =====================================================================
# 4. Smoke Test Probe Resilience & Retries
# =====================================================================


def test_smoke_test_retry_and_recovery(monkeypatch):
    """Verify smoke test recovers if server fails on attempt 1 but succeeds on 2."""
    call_counts = {"health": 0, "version": 0}

    def mock_make_request(url, timeout=5):
        if "health" in url:
            call_counts["health"] += 1
            if call_counts["health"] == 1:
                return 503, {"status": "starting"}, 20.0
            return (
                200,
                {
                    "status": "healthy",
                    "service": "test-service",
                    "environment": "staging",
                    "uptime_seconds": 5,
                    "version": "1.0.0",
                },
                15.0,
            )
        elif "version" in url:
            call_counts["version"] += 1
            return (
                200,
                {
                    "version": "1.0.0",
                    "commit_hash": "testsha",
                    "build_number": "42",
                },
                10.0,
            )
        return 404, None, 0.0

    monkeypatch.setattr("scripts.smoke_test.make_request", mock_make_request)

    success = run_smoke_tests("http://localhost:5000", max_retries=3, retry_delay=0)
    assert success is True
    assert call_counts["health"] == 2
    assert call_counts["version"] == 1


def test_smoke_test_all_attempts_fail(monkeypatch):
    """Verify smoke test exits with False when all connection attempts fail."""

    def mock_always_fail(url, timeout=5):
        raise urllib.error.URLError("Connection refused")

    monkeypatch.setattr("scripts.smoke_test.make_request", mock_always_fail)

    success = run_smoke_tests("http://localhost:5000", max_retries=2, retry_delay=0)
    assert success is False


def test_smoke_test_version_probe_failure(monkeypatch):
    """Verify smoke test fails if health succeeds but version probe returns 500."""

    def mock_health_ok_version_fail(url, timeout=5):
        if "health" in url:
            return (
                200,
                {
                    "status": "healthy",
                    "service": "test-service",
                    "environment": "staging",
                    "uptime_seconds": 1,
                    "version": "1.0.0",
                },
                10.0,
            )
        return 500, {"error": "Version service crashed"}, 15.0

    monkeypatch.setattr("scripts.smoke_test.make_request", mock_health_ok_version_fail)

    success = run_smoke_tests("http://localhost:5000", max_retries=1, retry_delay=0)
    assert success is False


# =====================================================================
# 5. Database Model Edge Cases
# =====================================================================


def test_deployment_model_get_latest_empty(app):
    """Verify get_latest_deployment returns None when no deployment exists for env."""
    with app.app_context():
        result = DeploymentModel.get_latest_deployment(
            "unknown_nonexistent_environment"
        )
        assert result is None


def test_pipeline_run_model_record_and_query(app):
    """Verify recording and querying recent pipeline runs."""
    with app.app_context():
        run = PipelineRunModel.record_run(
            workflow_name="security-ci.yml",
            branch="feature/hardened-gates",
            commit_sha="sec12345",
            lint_status="passed",
            security_status="passed",
            test_status="passed",
            build_status="passed",
            deploy_status="passed",
            overall_status="success",
            duration_seconds=4.25,
        )
        assert run is not None
        assert run["workflow_name"] == "security-ci.yml"
        assert run["commit_sha"] == "sec12345"

        recent = PipelineRunModel.get_recent_runs(limit=10)
        assert any(r["commit_sha"] == "sec12345" for r in recent)
