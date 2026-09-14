"""Configuration module for Docker Pulse Task and Ops Hub service.

Supports multi-environment resolution (Development, Testing, Production)
with dual PostgreSQL / SQLite database URLs and Redis caching.
"""

import os
import socket
import subprocess
from typing import Dict, Type


def _get_git_commit() -> str:
    """Extract the current Git short commit SHA with fallback."""
    env_sha = os.getenv("GIT_COMMIT_SHA")
    if env_sha:
        return env_sha[:7]
    try:
        output = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
        )
        return output.decode("utf-8").strip()
    except Exception:
        return "unknown"


class BaseConfig:
    """Base configuration defaults shared across all environments."""

    APP_NAME: str = "Docker Pulse Task Ops Hub"
    VERSION: str = "1.0.0"
    COMMIT_SHA: str = _get_git_commit()
    BUILD_NUMBER: str = os.getenv("BUILD_NUMBER", "local-dev")
    HOSTNAME: str = os.getenv("HOSTNAME", socket.gethostname())

    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
    JSON_SORT_KEYS: bool = False
    DEBUG: bool = False
    TESTING: bool = False

    # Database configuration (PostgreSQL or SQLite fallback)
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///data/tasks.db")
    DB_POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", "5"))
    DB_TIMEOUT: int = int(os.getenv("DB_TIMEOUT", "10"))

    # Redis cache configuration (Redis or in-memory fallback)
    REDIS_URL: str = os.getenv("REDIS_URL", "")
    CACHE_DEFAULT_TTL: int = int(os.getenv("CACHE_DEFAULT_TTL", "300"))


class DevelopmentConfig(BaseConfig):
    """Development environment configuration."""

    DEBUG: bool = True
    ENVIRONMENT: str = "development"


class TestingConfig(BaseConfig):
    """Testing environment configuration with in-memory storage."""

    TESTING: bool = True
    DEBUG: bool = True
    ENVIRONMENT: str = "testing"
    DATABASE_URL: str = "sqlite:///:memory:"
    REDIS_URL: str = ""  # Forces in-memory cache adapter


class ProductionConfig(BaseConfig):
    """Production environment configuration for containerized deployment."""

    DEBUG: bool = False
    TESTING: bool = False
    ENVIRONMENT: str = "production"
    SECRET_KEY: str = os.getenv("SECRET_KEY", "default-prod-change-me")


CONFIG_MAP: Dict[str, Type[BaseConfig]] = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config(env_name: str = None) -> Type[BaseConfig]:  # type: ignore
    """Resolve the configuration class based on environment name or FLASK_ENV."""
    if not env_name:
        env_name = os.getenv("FLASK_ENV", "development").lower()
    return CONFIG_MAP.get(env_name, DevelopmentConfig)
