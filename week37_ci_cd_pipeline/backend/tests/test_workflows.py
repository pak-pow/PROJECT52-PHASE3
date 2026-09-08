from pathlib import Path
import yaml
from scripts.smoke_test import run_smoke_tests

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
CI_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "ci.yml"
CD_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "cd.yml"


def test_ci_workflow_yaml_syntax_and_triggers():
    """Verify ci.yml is valid YAML and has proper branch and path triggers."""
    assert CI_WORKFLOW_PATH.exists(), f"ci.yml not found at {CI_WORKFLOW_PATH}"

    with open(CI_WORKFLOW_PATH, "r", encoding="utf-8") as f:
        ci = yaml.safe_load(f)

    # Check triggers
    # In PyYAML, unquoted 'on' is parsed as boolean True
    triggers = ci.get(True) or ci.get("on")
    assert triggers is not None, "Workflow missing triggers ('on')"
    assert "push" in triggers
    assert "pull_request" in triggers
    assert "main" in triggers["push"]["branches"]
    assert "develop" in triggers["push"]["branches"]


def test_ci_workflow_jobs_and_dependencies():
    """Verify ci.yml jobs structure, matrix strategy, and dependencies."""
    with open(CI_WORKFLOW_PATH, "r", encoding="utf-8") as f:
        ci = yaml.safe_load(f)

    jobs = ci.get("jobs", {})
    required_jobs = [
        "lint-and-format",
        "security-scan",
        "test-matrix",
        "build-artifact",
    ]
    for rj in required_jobs:
        assert rj in jobs, f"Job '{rj}' missing from ci.yml"

    # Test matrix verification
    matrix_job = jobs["test-matrix"]
    assert "needs" in matrix_job
    assert "lint-and-format" in matrix_job["needs"]
    assert "security-scan" in matrix_job["needs"]

    strategy = matrix_job.get("strategy", {})
    matrix = strategy.get("matrix", {})
    versions = matrix.get("python-version", [])
    assert "3.10" in versions
    assert "3.11" in versions
    assert "3.12" in versions

    # Build artifact verification
    build_job = jobs["build-artifact"]
    assert "needs" in build_job
    assert "test-matrix" in build_job["needs"]


def test_cd_workflow_yaml_syntax_and_stages():
    """Verify cd.yml triggers on main branch and tags,
    and gates production deployment."""
    assert CD_WORKFLOW_PATH.exists(), f"cd.yml not found at {CD_WORKFLOW_PATH}"

    with open(CD_WORKFLOW_PATH, "r", encoding="utf-8") as f:
        cd = yaml.safe_load(f)

    triggers = cd.get(True) or cd.get("on")
    assert "push" in triggers
    assert "main" in triggers["push"]["branches"]
    assert any("v*" in tag for tag in triggers["push"]["tags"])

    jobs = cd.get("jobs", {})
    assert "deploy-staging" in jobs
    assert "deploy-production" in jobs

    # Production must gate on staging success
    prod_job = jobs["deploy-production"]
    assert "needs" in prod_job
    assert "deploy-staging" in prod_job["needs"]


def test_smoke_test_probe_fails_gracefully_on_invalid_host():
    """Verify smoke_test.py returns False without crashing on unreachable port/host."""
    result = run_smoke_tests(
        base_url="http://127.0.0.1:59999",  # Nonexistent port
        max_retries=1,
        retry_delay=0.1,
    )
    assert result is False
