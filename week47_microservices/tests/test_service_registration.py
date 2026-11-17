"""Unit tests for ServiceRegistrar lifecycle and heartbeat client."""

import time
from unittest.mock import MagicMock, patch

from services.registry.instance_store import InstanceStore
from shared.models import HealthStatus
from shared.registration import ServiceRegistrar


def test_in_process_service_registration_lifecycle() -> None:
    """Verify in-process registration, heartbeat, and deregistration."""
    store = InstanceStore()
    registrar = ServiceRegistrar(
        service_name="user-service",
        port=8002,
        instance_store=store,
        heartbeat_interval=0.1,
    )

    # Register
    inst = registrar.register()
    assert inst is not None
    assert inst.service_name == "user-service"
    assert inst.health_status == HealthStatus.HEALTHY
    assert store.count() == 1

    # Single heartbeat
    assert registrar.heartbeat() is True

    # Background heartbeat thread
    registrar.start_heartbeat()
    time.sleep(0.2)

    # Deregister
    assert registrar.deregister() is True
    assert store.count() == 0


@patch("shared.registration.requests.post")
@patch("shared.registration.requests.delete")
def test_remote_http_service_registration(
    mock_delete: MagicMock, mock_post: MagicMock
) -> None:
    """Verify remote HTTP registration and heartbeat via REST endpoints."""
    # Mock registration response
    mock_reg_resp = MagicMock()
    mock_reg_resp.status_code = 201
    mock_reg_resp.json.return_value = {
        "service_name": "catalog-service",
        "instance_id": "catalog-8003",
        "host": "127.0.0.1",
        "port": 8003,
        "health_status": "HEALTHY",
    }
    mock_post.return_value = mock_reg_resp

    registrar = ServiceRegistrar(
        service_name="catalog-service",
        port=8003,
        registry_url="http://127.0.0.1:8001",
    )

    inst = registrar.register()
    assert inst is not None
    assert inst.service_name == "catalog-service"

    # Mock heartbeat
    mock_hb_resp = MagicMock()
    mock_hb_resp.status_code = 200
    mock_post.return_value = mock_hb_resp
    assert registrar.heartbeat() is True

    # Mock deregister
    mock_del_resp = MagicMock()
    mock_del_resp.status_code = 200
    mock_delete.return_value = mock_del_resp
    assert registrar.deregister() is True


@patch("shared.registration.requests.post")
def test_remote_registration_failure(mock_post: MagicMock) -> None:
    """Verify graceful handling when remote registry is unreachable."""
    mock_post.side_effect = Exception("Connection refused")

    registrar = ServiceRegistrar(
        service_name="order-service",
        port=8004,
        registry_url="http://127.0.0.1:8001",
    )
    assert registrar.register() is None
    assert registrar.heartbeat() is False
