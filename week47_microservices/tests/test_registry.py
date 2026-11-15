"""Unit and integration tests for PulseMesh Service Registry."""

import time

from flask.testing import FlaskClient

from services.registry.app import create_registry_app
from services.registry.instance_store import InstanceStore
from shared.config import TestingConfig
from shared.models import HealthStatus, ServiceInstance


def test_health_probe(client: FlaskClient) -> None:
    """Verify registry vitality health check endpoint."""
    res = client.get("/health")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "UP"
    assert data["service"] == "registry"
    assert data["registered_instances"] == 0


def test_register_instance_success(client: FlaskClient, sample_payload: dict) -> None:
    """Verify successful instance registration."""
    res = client.post("/api/v1/registry/register", json=sample_payload)
    assert res.status_code == 201
    data = res.get_json()
    assert data["service_name"] == "user-service"
    assert data["instance_id"] == "user-service-8002"
    assert data["host"] == "127.0.0.1"
    assert data["port"] == 8002
    assert data["health_status"] == "HEALTHY"
    assert data["base_url"] == "http://127.0.0.1:8002"
    assert "v1" in data["tags"]


def test_register_instance_generated_id(client: FlaskClient) -> None:
    """Verify instance registration with auto-generated instance_id."""
    payload = {
        "service_name": "catalog-service",
        "host": "127.0.0.1",
        "port": 8003,
    }
    res = client.post("/api/v1/registry/register", json=payload)
    assert res.status_code == 201
    data = res.get_json()
    assert data["service_name"] == "catalog-service"
    assert data["instance_id"].startswith("catalog-service-8003-")


def test_register_instance_validation_errors(client: FlaskClient) -> None:
    """Verify validation errors on malformed payloads."""
    # Non-JSON payload
    res = client.post(
        "/api/v1/registry/register",
        data="not json",
        content_type="text/plain",
    )
    assert res.status_code == 400
    assert res.get_json()["error"] == "invalid_payload"

    # Empty service name
    res = client.post(
        "/api/v1/registry/register",
        json={"service_name": "", "port": 8000},
    )
    assert res.status_code == 400
    assert res.get_json()["error"] == "validation_failed"

    # Empty host
    res = client.post(
        "/api/v1/registry/register",
        json={"service_name": "srv", "host": " ", "port": 8000},
    )
    assert res.status_code == 400

    # Invalid port (out of range)
    res = client.post(
        "/api/v1/registry/register",
        json={"service_name": "srv", "port": 70000},
    )
    assert res.status_code == 400

    # Invalid weight
    res = client.post(
        "/api/v1/registry/register",
        json={"service_name": "srv", "port": 8000, "weight": 0},
    )
    assert res.status_code == 400


def test_heartbeat_lifecycle(client: FlaskClient, sample_payload: dict) -> None:
    """Verify heartbeat refreshes and error handling."""
    # Register first
    client.post("/api/v1/registry/register", json=sample_payload)

    # Valid heartbeat via JSON body
    res = client.post(
        "/api/v1/registry/heartbeat",
        json={"instance_id": "user-service-8002"},
    )
    assert res.status_code == 200
    assert res.get_json()["instance_id"] == "user-service-8002"

    # Valid heartbeat via query parameter
    res = client.post("/api/v1/registry/heartbeat?instance_id=user-service-8002")
    assert res.status_code == 200

    # Missing instance_id
    res = client.post("/api/v1/registry/heartbeat", json={})
    assert res.status_code == 400
    assert res.get_json()["error"] == "missing_parameter"

    # Non-existent instance_id
    res = client.post(
        "/api/v1/registry/heartbeat",
        json={"instance_id": "non-existent-instance"},
    )
    assert res.status_code == 404
    assert res.get_json()["error"] == "instance_not_found"


def test_deregister_lifecycle(client: FlaskClient, sample_payload: dict) -> None:
    """Verify deregistration endpoint removes instance from store."""
    client.post("/api/v1/registry/register", json=sample_payload)

    # Missing instance_id
    res = client.delete("/api/v1/registry/deregister")
    assert res.status_code == 400

    # Valid deregister
    res = client.delete(
        "/api/v1/registry/deregister",
        json={"instance_id": "user-service-8002"},
    )
    assert res.status_code == 200
    assert res.get_json()["status"] == "deregistered"

    # Deregister again -> 404
    res = client.delete(
        "/api/v1/registry/deregister",
        json={"instance_id": "user-service-8002"},
    )
    assert res.status_code == 404


def test_services_queries_and_filtering(
    client: FlaskClient,
    store: InstanceStore,
) -> None:
    """Verify query endpoints for all services and service-specific filtering."""
    # Register multiple instances across services
    inst1 = ServiceInstance(
        service_name="order-service",
        instance_id="order-01",
        host="127.0.0.1",
        port=8004,
        health_status=HealthStatus.HEALTHY,
    )
    inst2 = ServiceInstance(
        service_name="order-service",
        instance_id="order-02",
        host="127.0.0.1",
        port=8014,
        health_status=HealthStatus.DEGRADED,
    )
    inst3 = ServiceInstance(
        service_name="catalog-service",
        instance_id="catalog-01",
        host="127.0.0.1",
        port=8003,
        health_status=HealthStatus.HEALTHY,
    )
    store.register(inst1)
    store.register(inst2)
    store.register(inst3)

    # Query all services
    res = client.get("/api/v1/registry/services")
    assert res.status_code == 200
    data = res.get_json()
    assert "order-service" in data
    assert "catalog-service" in data
    assert data["order-service"]["total_instances"] == 2
    assert data["order-service"]["healthy_instances"] == 1

    # Query order-service healthy only (default)
    res = client.get("/api/v1/registry/services/order-service")
    assert res.status_code == 200
    data = res.get_json()
    assert data["count"] == 1
    assert data["instances"][0]["instance_id"] == "order-01"

    # Query order-service all instances (healthy_only=false)
    res = client.get("/api/v1/registry/services/order-service?healthy_only=false")
    assert res.status_code == 200
    data = res.get_json()
    assert data["count"] == 2

    # Query single instance
    res = client.get("/api/v1/registry/instances/order-01")
    assert res.status_code == 200
    assert res.get_json()["instance_id"] == "order-01"

    # Query non-existent single instance
    res = client.get("/api/v1/registry/instances/non-existent")
    assert res.status_code == 404


def test_correlation_id_header(client: FlaskClient) -> None:
    """Verify X-Correlation-ID is preserved or generated on responses."""
    # When provided in request
    res = client.get("/health", headers={"X-Correlation-ID": "test-corr-12345"})
    assert res.headers.get("X-Correlation-ID") == "test-corr-12345"

    # When omitted in request -> auto-generated
    res2 = client.get("/health")
    assert res2.headers.get("X-Correlation-ID") is not None
    assert res2.headers.get("X-Correlation-ID").startswith("corr_")


def test_watchdog_evicts_stale_instances() -> None:
    """Verify HeartbeatWatchdog background thread purges expired instances."""
    store = InstanceStore()
    app = create_registry_app(
        config_class=TestingConfig,
        start_watchdog=True,
        instance_store=store,
    )

    # Register an instance with backdated heartbeat
    inst = ServiceInstance(
        service_name="worker-service",
        instance_id="worker-01",
        host="127.0.0.1",
        port=9000,
        last_heartbeat="2020-01-01T00:00:00+00:00",
    )
    store.register(inst, touch_heartbeat=False)
    assert store.count() == 1

    # Allow watchdog sweep to run (sweep interval is 0.5s in TestingConfig)
    time.sleep(0.8)

    # Instance should have been evicted
    assert store.count() == 0
    assert store.get_instance("worker-01") is None

    # Stop watchdog cleanly
    if hasattr(app, "watchdog") and app.watchdog:
        app.watchdog.stop(timeout=1.0)
