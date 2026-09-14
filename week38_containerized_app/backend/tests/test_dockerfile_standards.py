"""Automated tests validating Dockerfile standards and .dockerignore rules."""

from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
WEEK38_DIR = BACKEND_DIR.parent


def test_dockerfile_exists_and_is_multi_stage():
    """Verify Dockerfile uses multi-stage build (builder + runtime)."""
    dockerfile_path = BACKEND_DIR / "Dockerfile"
    assert dockerfile_path.exists(), "Dockerfile must exist in backend directory."

    content = dockerfile_path.read_text(encoding="utf-8")
    assert "FROM python:3.10-slim AS builder" in content
    assert "FROM python:3.10-slim AS runtime" in content
    assert "COPY --from=builder" in content


def test_dockerfile_non_root_user():
    """Verify Dockerfile drops root privileges to an unprivileged appuser."""
    content = (BACKEND_DIR / "Dockerfile").read_text(encoding="utf-8")
    assert "useradd -u 1001" in content
    assert "USER appuser" in content
    assert "--chown=appuser:appgroup" in content


def test_dockerfile_healthcheck_and_port():
    """Verify Dockerfile defines a HEALTHCHECK instruction and EXPOSE 5000."""
    content = (BACKEND_DIR / "Dockerfile").read_text(encoding="utf-8")
    assert "HEALTHCHECK" in content
    assert "/api/v1/health" in content
    assert "EXPOSE 5000" in content


def test_dockerfile_runs_gunicorn_in_production():
    """Verify production command launches Gunicorn WSGI server."""
    content = (BACKEND_DIR / "Dockerfile").read_text(encoding="utf-8")
    assert "gunicorn" in content
    assert "run:app" in content


def test_dockerignore_rules():
    """Verify .dockerignore excludes virtualenvs, git, tests, and databases."""
    dockerignore_path = BACKEND_DIR / ".dockerignore"
    assert dockerignore_path.exists(), ".dockerignore must exist in backend directory."

    rules = dockerignore_path.read_text(encoding="utf-8").splitlines()
    cleaned_rules = [r.strip() for r in rules if r.strip() and not r.startswith("#")]

    essential_patterns = [".git", "__pycache__/", ".venv/", ".env", "tests/", "*.db"]
    for pattern in essential_patterns:
        assert any(
            pattern in r for r in cleaned_rules
        ), f"Missing essential pattern {pattern} in .dockerignore"


def test_env_example_template():
    """Verify .env.example defines necessary environment variables."""
    env_example = WEEK38_DIR / ".env.example"
    assert env_example.exists(), ".env.example must exist in week38 directory."

    content = env_example.read_text(encoding="utf-8")
    assert "DATABASE_URL" in content
    assert "POSTGRES_USER" in content
    assert "REDIS_URL" in content
    assert "WEB_PORT" in content
