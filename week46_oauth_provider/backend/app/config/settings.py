"""Settings and environment profiles for PulseAuth OAuth 2.0 / OIDC provider."""

import os
from pathlib import Path
from typing import Type

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


class Config:
    """Base configuration with security defaults."""

    ENV = "base"
    DEBUG = False
    TESTING = False

    # Server & Issuer identity
    PORT = int(os.getenv("PORT", "5000"))
    ISSUER = os.getenv("PULSE_AUTH_ISSUER", f"http://127.0.0.1:{PORT}")

    # Secrets
    SECRET_KEY = os.getenv(
        "PULSE_AUTH_SECRET_KEY", "pulse_auth_insecure_development_secret_key_2026"
    )

    # Database & Storage
    DATA_DIR = BACKEND_DIR / "data"
    DATABASE_PATH = str(DATA_DIR / "pulse_auth.db")
    KEYS_DIR = DATA_DIR / "keys"
    RSA_PRIVATE_KEY_PATH = str(KEYS_DIR / "rsa_private.pem")
    RSA_PUBLIC_KEY_PATH = str(KEYS_DIR / "rsa_public.pem")

    # OAuth 2.0 / OIDC Expiration Windows (in seconds)
    AUTH_CODE_TTL_SECONDS = int(os.getenv("AUTH_CODE_TTL_SECONDS", "60"))
    ACCESS_TOKEN_TTL_SECONDS = int(os.getenv("ACCESS_TOKEN_TTL_SECONDS", "3600"))
    ID_TOKEN_TTL_SECONDS = int(os.getenv("ID_TOKEN_TTL_SECONDS", "3600"))
    REFRESH_TOKEN_TTL_SECONDS = int(
        os.getenv("REFRESH_TOKEN_TTL_SECONDS", str(30 * 24 * 3600))
    )

    # Cryptography
    RSA_KEY_SIZE = 2048
    JWT_ALGORITHM = "RS256"

    # Supported Scopes
    SUPPORTED_SCOPES = [
        "openid",
        "profile",
        "email",
        "offline_access",
        "read:documents",
        "write:documents",
    ]


class DevelopmentConfig(Config):
    """Development configuration profile."""

    ENV = "development"
    DEBUG = True


class TestingConfig(Config):
    """Testing configuration with temporary isolated database and keys."""

    ENV = "testing"
    TESTING = True
    DEBUG = True
    DATABASE_PATH = ":memory:"
    AUTH_CODE_TTL_SECONDS = 5
    ACCESS_TOKEN_TTL_SECONDS = 10
    ID_TOKEN_TTL_SECONDS = 10
    REFRESH_TOKEN_TTL_SECONDS = 20


class ProductionConfig(Config):
    """Hardened production configuration."""

    ENV = "production"
    DEBUG = False


def get_config(env_name: str | None = None) -> Type[Config]:
    """Resolve active configuration profile."""
    target = env_name or os.getenv("FLASK_ENV", "development").lower()
    if target in ("prod", "production"):
        return ProductionConfig
    if target in ("test", "testing"):
        return TestingConfig
    return DevelopmentConfig
