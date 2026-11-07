"""Pytest fixtures and isolated configuration for PulseAuth test suite."""

import sys
from pathlib import Path
from typing import Generator

import pytest
from flask import Flask
from flask.testing import FlaskClient

# Ensure backend package is on sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app import create_app  # noqa: E402
from app.config.settings import TestingConfig  # noqa: E402
from app.crypto.rsa_manager import RSAKeyManager  # noqa: E402
from app.db.connection import init_db  # noqa: E402
from data.seed import seed_database  # noqa: E402


@pytest.fixture
def app(tmp_path: Path) -> Generator[Flask, None, None]:
    """Provide an isolated Flask application instance with temporary files."""
    db_file = str(tmp_path / "test_pulse_auth.db")
    keys_dir = tmp_path / "keys"
    keys_dir.mkdir(parents=True, exist_ok=True)

    priv_path = str(keys_dir / "rsa_private.pem")
    pub_path = str(keys_dir / "rsa_public.pem")

    class TestConfig(TestingConfig):
        DATABASE_PATH = db_file
        RSA_PRIVATE_KEY_PATH = priv_path
        RSA_PUBLIC_KEY_PATH = pub_path
        DATA_DIR = tmp_path

    app_instance = create_app(TestConfig)

    with app_instance.app_context():
        init_db(db_file)
        yield app_instance


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    """Provide a test client for issuing HTTP requests."""
    return app.test_client()


@pytest.fixture
def seeded_db(app: Flask) -> None:
    """Populate temporary database with standard demo users and clients."""
    with app.app_context():
        seed_database(app.config["DATABASE_PATH"])


@pytest.fixture
def rsa_manager(tmp_path: Path) -> RSAKeyManager:
    """Provide a standalone ephemeral RSAKeyManager."""
    priv = tmp_path / "standalone_priv.pem"
    pub = tmp_path / "standalone_pub.pem"
    return RSAKeyManager(
        private_key_path=str(priv),
        public_key_path=str(pub),
        auto_generate=True,
        key_size=2048,
    )
