"""Configuration module for PulsePad collaborative editor."""

import os
from pathlib import Path


class Config:
    """Base application configuration."""

    BASE_DIR = Path(__file__).resolve().parent.parent.parent
    DATA_DIR = BASE_DIR / "data"
    DB_PATH = os.getenv("DB_PATH", str(DATA_DIR / "pulsepad.db"))
    SECRET_KEY = os.getenv("SECRET_KEY", "pulsepad-dev-secret-key-change-in-prod")
    CORS_ALLOWED_ORIGINS = os.getenv("CORS_ALLOWED_ORIGINS", "*").split(",")
    DEBUG = os.getenv("FLASK_DEBUG", "0") == "1"
    TESTING = False
    AUTO_SAVE_INTERVAL_SEC = int(os.getenv("AUTO_SAVE_INTERVAL_SEC", "3"))


class TestingConfig(Config):
    """Test environment configuration."""

    TESTING = True
    DB_PATH = ":memory:"
    DEBUG = False
