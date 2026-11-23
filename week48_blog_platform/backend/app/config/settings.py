"""Application configuration settings for PulsePress."""

import os
from pathlib import Path
from typing import Type

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BACKEND_DIR / "data"
FRONTEND_DIR = BACKEND_DIR.parent / "frontend"


class Config:
    """Base configuration with defaults."""

    SECRET_KEY = os.getenv("SECRET_KEY", "pulsepress_insecure_default_secret_key_2026")
    SITE_NAME = os.getenv("SITE_NAME", "PulsePress")
    SITE_URL = os.getenv("SITE_URL", "http://localhost:5000")
    SITE_DESCRIPTION = os.getenv(
        "SITE_DESCRIPTION",
        "A full-featured technical blog with advanced SEO and full-text search.",
    )
    DEFAULT_AUTHOR_NAME = os.getenv("DEFAULT_AUTHOR_NAME", "PulsePress Team")
    WORDS_PER_MINUTE = int(os.getenv("WORDS_PER_MINUTE", "200"))
    DEFAULT_PAGE_SIZE = int(os.getenv("DEFAULT_PAGE_SIZE", "10"))
    MAX_PAGE_SIZE = int(os.getenv("MAX_PAGE_SIZE", "50"))
    COMMENT_RATE_LIMIT_MINUTES = int(os.getenv("COMMENT_RATE_LIMIT_MINUTES", "10"))
    COMMENT_RATE_LIMIT_MAX = int(os.getenv("COMMENT_RATE_LIMIT_MAX", "5"))

    DB_PATH = Path(os.getenv("DB_PATH", str(DATA_DIR / "pulsepress.db")))
    SCHEMA_PATH = Path(os.getenv("SCHEMA_PATH", str(DATA_DIR / "schema.sql")))
    FRONTEND_DIR = FRONTEND_DIR


class DevelopmentConfig(Config):
    """Development environment configuration."""

    DEBUG = True
    TESTING = False


class TestingConfig(Config):
    """Testing environment configuration."""

    DEBUG = True
    TESTING = True
    DB_PATH = ":memory:"


class ProductionConfig(Config):
    """Production environment configuration."""

    DEBUG = False
    TESTING = False


CONFIG_MAP = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config(env_name: str = "") -> Type[Config]:
    """Retrieve configuration class matching environment name."""
    env = env_name or os.getenv("FLASK_ENV", "development").lower()
    return CONFIG_MAP.get(env, DevelopmentConfig)
