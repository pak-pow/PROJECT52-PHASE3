"""Application settings and configuration environments for PulseInfer."""

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
    MODELS_VAULT_DIR: Path = DATA_DIR / "models_vault"

    # Database
    DB_PATH: Path = DATA_DIR / "pulseinfer.db"
    SCHEMA_PATH: Path = DATA_DIR / "schema.sql"

    # Inference Serving Parameters
    MAX_BATCH_SIZE: int = 32
    BATCH_TIMEOUT_MS: float = 10.0
    CACHE_MAX_SIZE: int = 1000
    CACHE_TTL_SECONDS: int = 300
    SLIDING_WINDOW_METRICS_SIZE: int = 500
    MAX_CONTENT_LENGTH: int = 16 * 1024 * 1024  # 16 MB

    # Model Domain Declarations
    SUPPORTED_DOMAINS: Dict[str, str] = {
        "nlp": "Natural Language Processing",
        "vision": "Computer Vision",
        "tabular": "Tabular Data & Risk Scoring",
    }

    TESTING: bool = False
    DEBUG: bool = False


class DevelopmentConfig(Config):
    """Development configuration."""

    DEBUG: bool = True


class TestingConfig(Config):
    """Testing configuration with in-memory database."""

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
