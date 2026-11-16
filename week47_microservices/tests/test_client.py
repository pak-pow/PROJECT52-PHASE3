"""Unit tests for resilient inter-service client (PulseClient)."""

from unittest.mock import MagicMock

import pytest
import requests

from services.registry.instance_store import InstanceStore
from shared.circuit_breaker import (
    CircuitBreakerOpenException,
    CircuitBreakerRegistry,
    CircuitState,
)
from shared.client import PulseClient, PulseResponse
from shared.models import (
    CorrelationContext,
    HealthStatus,
    ServiceInstance,
)


@pytest.fixture
def mock_session() -> MagicMock:
    """Fixture providing a mock requests.Session."""
    return MagicMock(spec=requests.Session)


@pytest.fixture
def store_with_instances() -> InstanceStore:
    """Fixture providing an InstanceStore populated with service instances."""
    store = InstanceStore()
    inst1 = ServiceInstance(
        service_name="user-service",
        instance_id="user-01",
        host="127.0.0.1",
        port=8002,
        health_status=HealthStatus.HEALTHY,
    )
    inst2 = ServiceInstance(
        service_name="user-service",
        instance_id="user-02",
        host="127.0.0.1",
        port=8012,
        health_status=HealthStatus.HEALTHY,
    )
    store.register(inst1)
    store.register(inst2)
    return store


def test_pulse_response_methods() -> None:
    """Verify PulseResponse envelope attributes and json parsing."""
    resp = PulseResponse(
        status_code=200,
        headers={"Content-Type": "application/json"},
        data={"user_id": "u123", "role": "admin"},
        raw_text='{"user_id": "u123", "role": "admin"}',
        latency_ms=12.5,
        instance_id="user-01",
        service_name="user-service",
    )
    assert resp.is_success is True
    assert resp.json()["role"] == "admin"

    # When data is string but raw_text is valid JSON
    resp_raw = PulseResponse(
        status_code=200,
        headers={},
        data="raw_payload",
        raw_text='{"status": "ok", "code": 1}',
        latency_ms=4.0,
        instance_id="user-01",
        service_name="user-service",
    )
    assert resp_raw.json()["code"] == 1

    # When data is text
    resp_text = PulseResponse(
        status_code=200,
        headers={},
        data="OK",
        raw_text="OK",
        latency_ms=5.0,
        instance_id="user-01",
        service_name="user-service",
    )
    assert resp_text.is_success is True


def test_resolve_instances(
    mock_session: MagicMock, store_with_instances: InstanceStore
) -> None:
    """Verify instance resolution from local store, remote registry, and fallback."""
    # From local store
    client_local = PulseClient(
        instance_store=store_with_instances,
        session=mock_session,
    )
    instances = client_local.resolve_instances("user-service")
    assert len(instances) == 2

    # From remote discovery URL
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "instances": [
            {
                "service_name": "remote-svc",
                "instance_id": "remote-01",
                "host": "10.0.0.1",
                "port": 9000,
            }
        ]
    }
    mock_session.get.return_value = mock_resp

    client_remote = PulseClient(
        discovery_url="http://127.0.0.1:8001",
        session=mock_session,
    )
    instances_rem = client_remote.resolve_instances("remote-svc")
    assert len(instances_rem) == 1
    assert instances_rem[0].instance_id == "remote-01"

    # From default fallback port map
    client_fallback = PulseClient(session=mock_session)
    instances_fb = client_fallback.resolve_instances("order-service")
    assert len(instances_fb) == 1
    assert instances_fb[0].port == 8004


def test_client_request_success(
    mock_session: MagicMock, store_with_instances: InstanceStore
) -> None:
    """Verify successful request execution through PulseClient."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"X-Server": "user-service"}
    mock_resp.json.return_value = {"id": "usr_100", "name": "Jane"}
    mock_resp.text = '{"id": "usr_100", "name": "Jane"}'
    mock_session.request.return_value = mock_resp

    client = PulseClient(
        instance_store=store_with_instances,
        session=mock_session,
    )

    with CorrelationContext.scope("corr_test_999"):
        resp = client.get("user-service", "/api/v1/users/usr_100")

    assert resp.status_code == 200
    assert resp.json()["id"] == "usr_100"
    assert resp.service_name == "user-service"

    # Verify correlation ID was passed in headers
    _, kwargs = mock_session.request.call_args
    assert kwargs["headers"]["X-Correlation-ID"] == "corr_test_999"


def test_client_request_retry_on_server_error(
    mock_session: MagicMock, store_with_instances: InstanceStore
) -> None:
    """Verify client retries on transient 500 server error and succeeds."""
    err_resp = MagicMock()
    err_resp.status_code = 500
    err_resp.text = "Internal Server Error"
    err_resp.json.side_effect = ValueError("Not JSON")

    ok_resp = MagicMock()
    ok_resp.status_code = 200
    ok_resp.headers = {}
    ok_resp.json.return_value = {"status": "recovered"}
    ok_resp.text = '{"status": "recovered"}'

    # First call fails with 500, second call succeeds with 200
    mock_session.request.side_effect = [err_resp, ok_resp]

    client = PulseClient(
        instance_store=store_with_instances,
        session=mock_session,
        max_retries=2,
        retry_backoff_factor=0.01,
    )

    resp = client.post("user-service", "/api/v1/users", json={"name": "Alice"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "recovered"
    assert mock_session.request.call_count == 2


def test_client_request_sustained_failure_trips_breaker(
    mock_session: MagicMock, store_with_instances: InstanceStore
) -> None:
    """Verify sustained errors trip circuit breaker."""
    err_resp = MagicMock()
    err_resp.status_code = 500
    err_resp.headers = {}
    err_resp.text = "Error"
    err_resp.json.side_effect = ValueError("Not JSON")
    mock_session.request.return_value = err_resp

    cb_registry = CircuitBreakerRegistry()
    client = PulseClient(
        instance_store=store_with_instances,
        circuit_breaker_registry=cb_registry,
        session=mock_session,
        max_retries=1,
    )

    cb = cb_registry.get("user-service", failure_threshold=2)

    # First failing request -> failure_count = 1
    client.get("user-service", "/fail")
    assert cb.failure_count == 1
    assert cb.state == CircuitState.CLOSED

    # Second failing request -> failure_count = 2 -> trips to OPEN
    client.get("user-service", "/fail")
    assert cb.state == CircuitState.OPEN

    # Next call immediately fails fast with CircuitBreakerOpenException
    with pytest.raises(CircuitBreakerOpenException):
        client.get("user-service", "/fail")


def test_client_network_exception_handling(
    mock_session: MagicMock, store_with_instances: InstanceStore
) -> None:
    """Verify network connection errors trigger retry and then raise."""
    mock_session.request.side_effect = requests.ConnectionError("Connection refused")

    client = PulseClient(
        instance_store=store_with_instances,
        session=mock_session,
        max_retries=2,
        retry_backoff_factor=0.01,
    )

    with pytest.raises(requests.ConnectionError):
        client.get("user-service", "/timeout")

    assert mock_session.request.call_count == 2


def test_client_convenience_methods(
    mock_session: MagicMock, store_with_instances: InstanceStore
) -> None:
    """Verify put and delete convenience methods."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {}
    mock_resp.json.return_value = {"status": "ok"}
    mock_resp.text = '{"status": "ok"}'
    mock_session.request.return_value = mock_resp

    client = PulseClient(
        instance_store=store_with_instances,
        session=mock_session,
    )

    put_resp = client.put("user-service", "/update", json={"active": True})
    assert put_resp.status_code == 200

    del_resp = client.delete("user-service", "/delete")
    assert del_resp.status_code == 200


def test_client_no_instances_error(mock_session: MagicMock) -> None:
    """Verify error raised when service has no discoverable instances."""
    client = PulseClient(session=mock_session)
    client.resolve_instances = MagicMock(return_value=[])  # type: ignore

    with pytest.raises(RuntimeError) as exc_info:
        client.get("unknown-service", "/data")
    assert "No instances discovered" in str(exc_info.value)
