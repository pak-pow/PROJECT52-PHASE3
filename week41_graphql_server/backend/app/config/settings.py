import os
from pathlib import Path


class Config:
    """Application configuration defaults."""

    BASE_DIR = Path(__file__).resolve().parent.parent.parent
    DATA_DIR = BASE_DIR / "data"
    DB_PATH = os.environ.get("PULSEGRAPH_DB_PATH", str(DATA_DIR / "pulsegraph.db"))
    SCHEMA_PATH = str(DATA_DIR / "schema.sql")
    SECRET_KEY = os.environ.get("SECRET_KEY", "pulsegraph-dev-secret-key-2026")
    TESTING = False
    DEBUG = False
    CORS_ORIGIN = os.environ.get("CORS_ORIGIN", "*")


class TestingConfig(Config):
    """Testing configuration overrides."""

    TESTING = True
    DEBUG = True
    DB_PATH = os.environ.get(
        "PULSEGRAPH_TEST_DB_PATH", str(Config.DATA_DIR / "test_pulsegraph.db")
    )
