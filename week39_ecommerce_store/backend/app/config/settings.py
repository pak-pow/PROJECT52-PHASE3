import os
import subprocess
from pathlib import Path


def _get_git_commit():
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        return commit
    except Exception:
        return "unknown"


class BaseConfig:
    ENV = os.getenv("FLASK_ENV", "production")
    DEBUG = False
    TESTING = False
    PORT = int(os.getenv("PORT", "5000"))
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-prod")
    APP_VERSION = "1.0.0"
    GIT_COMMIT = _get_git_commit()

    BASE_DIR = Path(__file__).resolve().parent.parent.parent
    DATABASE_PATH = os.getenv("DATABASE_PATH", str(BASE_DIR / "data" / "store.db"))


class DevelopmentConfig(BaseConfig):
    ENV = "development"
    DEBUG = True


class TestingConfig(BaseConfig):
    ENV = "testing"
    TESTING = True
    DEBUG = True
    DATABASE_PATH = ":memory:"
    SECRET_KEY = "testing-secret-key"


class ProductionConfig(BaseConfig):
    ENV = "production"
    DEBUG = False


_CONFIG_MAP = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config(env_name=None):
    if env_name is None:
        env_name = os.getenv("FLASK_ENV", "development").lower()
    return _CONFIG_MAP.get(env_name, DevelopmentConfig)
