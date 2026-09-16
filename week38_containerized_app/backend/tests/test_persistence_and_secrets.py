"""Automated tests for Day 4 persistence, migrations, and secrets handling."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from app.config.settings import get_secret
from app.db import init_db
from scripts.init_db import (
    record_migration,
    run_migrations,
    seed_demo_tasks,
    setup_migrations_table,
)
from scripts.verify_persistence import verify_canary, write_canary

WEEK38_DIR = Path(__file__).resolve().parent.parent.parent


@pytest.fixture
def test_db(tmp_path):
    """Provide isolated SQLite database URL for persistence testing."""
    db_file = tmp_path / "test_persistence.db"
    db_url = f"sqlite:///{db_file.as_posix()}"
    init_db(db_url)
    return db_url


def test_get_secret_direct_env(monkeypatch):
    """Verify get_secret retrieves directly from environment variable."""
    monkeypatch.setenv("TEST_KEY", "direct-env-value")
    val = get_secret("TEST_KEY", default="fallback")
    assert val == "direct-env-value"


def test_get_secret_from_file(monkeypatch):
    """Verify get_secret retrieves from a file path specified by _FILE variable."""
    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as tf:
        tf.write("secret-from-file-content\n")
        tf_path = tf.name

    try:
        monkeypatch.setenv("API_KEY_FILE", tf_path)
        monkeypatch.delenv("API_KEY", raising=False)
        val = get_secret("API_KEY", default="fallback")
        assert val == "secret-from-file-content"
    finally:
        if os.path.exists(tf_path):
            os.remove(tf_path)


def test_get_secret_from_docker_secrets_dir(monkeypatch):
    """Verify get_secret retrieves from /run/secrets/ standard Docker path."""
    monkeypatch.delenv("DB_PASS_FILE", raising=False)
    monkeypatch.delenv("DB_PASS", raising=False)

    with patch("app.config.settings.Path.exists") as mock_exists, patch(
        "app.config.settings.Path.is_file"
    ) as mock_is_file, patch("app.config.settings.Path.read_text") as mock_read_text:
        mock_exists.return_value = True
        mock_is_file.return_value = True
        mock_read_text.return_value = "docker-vault-secret\n"

        val = get_secret("DB_PASS", default="fallback")
        assert val == "docker-vault-secret"


def test_get_secret_default_fallback(monkeypatch):
    """Verify get_secret falls back to default when neither env nor file exists."""
    monkeypatch.delenv("NON_EXISTENT_KEY", raising=False)
    monkeypatch.delenv("NON_EXISTENT_KEY_FILE", raising=False)
    val = get_secret("NON_EXISTENT_KEY", default="my-fallback-val")
    assert val == "my-fallback-val"


def test_get_secret_file_error_fallback(monkeypatch):
    """Verify get_secret falls back when file is invalid or raises OSError."""
    monkeypatch.setenv("FAULTY_KEY_FILE", "/non/existent/path/for/secret/12345.txt")
    monkeypatch.setenv("FAULTY_KEY", "env-fallback")
    val = get_secret("FAULTY_KEY", default="default")
    assert val == "env-fallback"


def test_init_db_script_workflow(test_db):
    """Verify migration script sets up tables, tracks baseline, and seeds demo tasks."""
    setup_migrations_table(db_url=test_db)

    # Record baseline migration
    recorded = record_migration("v1.0.0_test", "Test migration", db_url=test_db)
    assert recorded is True

    # Second attempt should return False (already recorded)
    duplicate = record_migration("v1.0.0_test", "Duplicate migration", db_url=test_db)
    assert duplicate is False

    # Seed demo tasks
    seeded = seed_demo_tasks(db_url=test_db)
    assert seeded == 3

    # Running seed again should do nothing (table not empty)
    seeded_again = seed_demo_tasks(db_url=test_db)
    assert seeded_again == 0


def test_run_migrations_full_cycle(test_db):
    """Verify run_migrations performs end-to-end initialization."""
    res = run_migrations(db_url=test_db, seed=True)
    assert res["status"] == "success"
    assert "database_engine" in res


def test_verify_persistence_cycle(test_db):
    """Verify write_canary and verify_canary functions."""
    write_res = write_canary(db_url=test_db, canary_id="test-canary-01")
    assert write_res["canary_id"] == "test-canary-01"

    verify_res = verify_canary("test-canary-01", db_url=test_db)
    assert verify_res["canary_id"] == "test-canary-01"
    assert verify_res["database_persisted"] is True
    assert verify_res["db_record"]["title"] == "Persistence Canary [test-canary-01]"


def test_compose_override_file_structure():
    """Verify docker-compose.override.yml defines development mounts and ports."""
    override_path = WEEK38_DIR / "docker-compose.override.yml"
    assert override_path.exists(), "docker-compose.override.yml must exist."

    content = override_path.read_text(encoding="utf-8")
    assert "FLASK_ENV: development" in content
    assert "./backend:/app" in content
    assert "5000:5000" in content
    assert "5432:5432" in content
    assert "6379:6379" in content


def test_compose_prod_file_structure():
    """Verify docker-compose.prod.yml defines resource limits and secrets."""
    prod_path = WEEK38_DIR / "docker-compose.prod.yml"
    assert prod_path.exists(), "docker-compose.prod.yml must exist."

    content = prod_path.read_text(encoding="utf-8")
    assert "restart: always" in content
    assert "resources:" in content
    assert "limits:" in content
    assert "memory:" in content
    assert "secrets:" in content
    assert "api_secret_key" in content
    assert "json-file" in content
