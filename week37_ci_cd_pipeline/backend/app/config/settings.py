import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class BaseConfig:
    """Base application configuration."""

    APP_NAME = "CI/CD Deployment Monitor Service"
    APP_VERSION = os.getenv("APP_VERSION", "1.0.0")
    BUILD_NUMBER = os.getenv("BUILD_NUMBER", "dev-local")
    GIT_COMMIT_HASH = os.getenv("GIT_COMMIT_HASH", "latest-commit")
    SECRET_KEY = os.getenv("SECRET_KEY", "ci-cd-dev-insecure-secret-key")
    DEBUG = False
    TESTING = False
    DATABASE_PATH = os.getenv(
        "DATABASE_PATH", str(BASE_DIR / "data" / "deployments.db")
    )
    AUTO_SEEDED = True


class DevelopmentConfig(BaseConfig):
    """Configuration for local development."""

    DEBUG = True
    ENV = "development"


class TestingConfig(BaseConfig):
    """Configuration for automated test execution."""

    TESTING = True
    DEBUG = True
    ENV = "testing"
    DATABASE_PATH = str(BASE_DIR / "data" / "test_deployments.db")


class StagingConfig(BaseConfig):
    """Configuration for staging / pre-production validation."""

    DEBUG = False
    ENV = "staging"


class ProductionConfig(BaseConfig):
    """Configuration for live production release."""

    DEBUG = False
    ENV = "production"
    SECRET_KEY = os.getenv("SECRET_KEY", "prod-must-be-set-via-environment-var")


CONFIG_MAP = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "staging": StagingConfig,
    "production": ProductionConfig,
}


def get_config(env_name=None):
    """Resolve environment configuration class based on environment variable."""
    if not env_name:
        env_name = os.getenv("FLASK_ENV", "development").lower()
    return CONFIG_MAP.get(env_name, DevelopmentConfig)
