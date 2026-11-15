"""Pytest fixtures for PulseMesh test suites."""

from typing import Any, Generator

import pytest
from flask import Flask
from flask.testing import FlaskClient

from services.registry.app import create_registry_app
from services.registry.instance_store import InstanceStore
from shared.config import TestingConfig


@pytest.fixture
def store() -> InstanceStore:
    """Fixture providing a fresh isolated InstanceStore."""
    return InstanceStore()


@pytest.fixture
def app(store: InstanceStore) -> Generator[Flask, None, None]:
    """Fixture providing an isolated Registry Flask application."""
    test_app = create_registry_app(
        config_class=TestingConfig,
        start_watchdog=False,
        instance_store=store,
    )
    yield test_app


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    """Fixture providing a test client for the Registry application."""
    return app.test_client()


@pytest.fixture
def sample_payload() -> dict[str, Any]:
    """Fixture providing a valid service registration payload."""
    return {
        "service_name": "user-service",
        "instance_id": "user-service-8002",
        "host": "127.0.0.1",
        "port": 8002,
        "tags": ["v1", "production"],
        "weight": 2,
        "metadata": {"region": "us-east-1"},
    }
