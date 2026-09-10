from app.config.settings import (
    DevelopmentConfig,
    ProductionConfig,
    StagingConfig,
    TestingConfig,
    get_config,
)


def test_health_check_endpoint(client):
    """Verify GET /api/v1/health returns healthy status and uptime."""
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "healthy"
    assert "uptime_seconds" in data
    assert data["environment"] == "testing"
    assert "version" in data


def test_version_endpoint(client):
    """Verify GET /api/v1/version returns semantic version and build info."""
    res = client.get("/api/v1/version")
    assert res.status_code == 200
    data = res.get_json()
    assert "version" in data
    assert "commit_hash" in data
    assert "build_number" in data
    assert data["environment"] == "testing"


def test_environment_configuration_resolver():
    """Verify get_config resolves correct configuration classes."""
    assert get_config("development") == DevelopmentConfig
    assert get_config("testing") == TestingConfig
    assert get_config("staging") == StagingConfig
    assert get_config("production") == ProductionConfig
    # Fallback to Development
    assert get_config("nonexistent_env") == DevelopmentConfig
