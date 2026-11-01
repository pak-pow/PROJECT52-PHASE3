"""Application settings and configuration environments for PulseSub."""

import os
from pathlib import Path
from typing import Any, Dict, Optional


class Config:
    """Base application configuration."""

    # Base filesystem paths
    APP_DIR: Path = Path(__file__).resolve().parent.parent
    BACKEND_DIR: Path = APP_DIR.parent
    PROJECT_DIR: Path = BACKEND_DIR.parent
    FRONTEND_DIR: Path = PROJECT_DIR / "frontend"
    DATA_DIR: Path = BACKEND_DIR / "data"

    # Database
    DB_PATH: Path = DATA_DIR / "pulsesub.db"
    SCHEMA_PATH: Path = DATA_DIR / "schema.sql"

    # Security & Webhook Signatures
    SECRET_KEY: str = os.getenv("SECRET_KEY", "pulsesub_super_secret_jwt_key_2026")
    WEBHOOK_SIGNING_SECRET: str = os.getenv(
        "WEBHOOK_SIGNING_SECRET", "whsec_pulsesub_test_secret_key_2026"
    )
    WEBHOOK_TIMESTAMP_TOLERANCE_SECONDS: int = 300

    # Billing & Entitlements Rules
    ANNUAL_DISCOUNT_PERCENTAGE: int = 20
    OVER_QUOTA_ALERT_THRESHOLDS: list[float] = [0.80, 0.90, 1.00]

    TESTING: bool = False
    DEBUG: bool = False


class DevelopmentConfig(Config):
    """Development configuration with debug mode enabled."""

    DEBUG: bool = True


class TestingConfig(Config):
    """Testing configuration with isolated in-memory database."""

    TESTING: bool = True
    DEBUG: bool = True
    DB_PATH: str = ":memory:"


class ProductionConfig(Config):
    """Production configuration."""

    DEBUG: bool = False


CONFIG_MAP: Dict[str, Any] = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config(env_name: Optional[str] = None) -> Any:
    """Retrieve configuration class based on environment name or ENV variable."""
    env = env_name or os.getenv("FLASK_ENV", "development").lower()
    return CONFIG_MAP.get(env, DevelopmentConfig)
