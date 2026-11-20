"""Unit and integration tests for Interactive Topology & Chaos Engineering Console."""

from gateway.app import create_gateway_app
from services.registry.instance_store import InstanceStore
from shared.message_broker import MessageBroker
from shared.models import CloudEvent, HealthStatus, ServiceInstance


def test_console_html_and_static_assets():
    """Test gateway serves /console HTML and static CSS/JS files."""
    app = create_gateway_app()
    client = app.test_client()

    # 1. Console HTML
    res = client.get("/console")
    assert res.status_code == 200
    assert "text/html" in res.headers.get("Content-Type", "")
    assert "PULSEMESH // DISTRIBUTED ARCHITECTURE" in res.data.decode("utf-8")

    # 2. Static CSS
    res_css = client.get("/static/css/styles.css")
    assert res_css.status_code == 200
    assert "text/css" in res_css.headers.get("Content-Type", "")

    # 3. Static JS
    res_js = client.get("/static/js/app.js")
    assert res_js.status_code == 200
    assert "javascript" in res_js.headers.get("Content-Type", "")


def test_chaos_circuit_breaker_endpoints():
    """Test chaos endpoints to manually trip and reset circuit breakers."""
    app = create_gateway_app()
    client = app.test_client()

    # 1. Validation error - missing service_name
    res_bad = client.post("/api/v1/chaos/circuit/trip", json={})
    assert res_bad.status_code == 400

    # 2. Trip catalog-service breaker
    res_trip = client.post(
        "/api/v1/chaos/circuit/trip", json={"service_name": "catalog-service"}
    )
    assert res_trip.status_code == 200
    assert res_trip.json["state"] == "OPEN"
    assert res_trip.json["service_name"] == "catalog-service"

    # 3. Reset catalog-service breaker
    res_reset = client.post(
        "/api/v1/chaos/circuit/reset", json={"service_name": "catalog-service"}
    )
    assert res_reset.status_code == 200
    assert res_reset.json["state"] == "CLOSED"

    # 4. Reset validation error
    res_reset_bad = client.post("/api/v1/chaos/circuit/reset", json={})
    assert res_reset_bad.status_code == 400


def test_chaos_instance_status_update():
    """Test dynamically modifying an instance health status via chaos API."""
    store = InstanceStore()
    inst = ServiceInstance(
        service_name="user-service",
        instance_id="user-01",
        host="127.0.0.1",
        port=8002,
        health_status=HealthStatus.HEALTHY,
    )
    store.register(inst)

    app = create_gateway_app(instance_store=store)
    client = app.test_client()

    # 1. Validation error - missing parameters
    assert client.post("/api/v1/chaos/instance/status", json={}).status_code == 400

    # 2. Non-existent instance
    res_404 = client.post(
        "/api/v1/chaos/instance/status",
        json={"instance_id": "missing-inst", "health_status": "DOWN"},
    )
    assert res_404.status_code == 404

    # 3. Invalid health status string
    res_inv = client.post(
        "/api/v1/chaos/instance/status",
        json={"instance_id": "user-01", "health_status": "INVALID_STATE"},
    )
    assert res_inv.status_code == 400

    # 4. Successful status update
    res_ok = client.post(
        "/api/v1/chaos/instance/status",
        json={"instance_id": "user-01", "health_status": "DOWN"},
    )
    assert res_ok.status_code == 200
    assert res_ok.json["health_status"] == "DOWN"
    assert store.get_instance("user-01").health_status == HealthStatus.DOWN


def test_load_balancer_strategy_runtime_switch():
    """Test dynamically updating the gateway default load balancing strategy."""
    app = create_gateway_app()
    client = app.test_client()

    # 1. Missing strategy parameter
    assert (
        client.post("/api/v1/gateway/load-balancer/strategy", json={}).status_code
        == 400
    )

    # 2. Unknown strategy algorithm
    res_unk = client.post(
        "/api/v1/gateway/load-balancer/strategy",
        json={"strategy": "NON_EXISTENT_ALGO"},
    )
    assert res_unk.status_code == 400

    # 3. Successful strategy updates
    res_lc = client.post(
        "/api/v1/gateway/load-balancer/strategy",
        json={"strategy": "LEAST_CONNECTIONS"},
    )
    assert res_lc.status_code == 200
    assert res_lc.json["strategy"] == "LEAST_CONNECTIONS"

    res_lw = client.post(
        "/api/v1/gateway/load-balancer/strategy",
        json={"strategy": "LATENCY_WEIGHTED"},
    )
    assert res_lw.status_code == 200
    assert res_lw.json["strategy"] == "LATENCY_WEIGHTED"


def test_broker_management_endpoints():
    """Test gateway broker history, DLQ querying, replaying, and purging."""
    broker = MessageBroker()
    app = create_gateway_app(broker=broker)
    client = app.test_client()

    # 1. Seed CloudEvent to topic history
    evt = CloudEvent.create(
        source="order-service",
        event_type="order.completed",
        data={"order_id": "ord_broker_test"},
    )
    broker.publish("orders.events", evt)

    # Query events
    res_events = client.get("/api/v1/broker/events?topic=orders.events")
    assert res_events.status_code == 200
    assert res_events.json["count"] == 1
    assert res_events.json["events"][0]["id"] == evt.id

    # 2. Query empty DLQ
    res_dlq = client.get("/api/v1/broker/dlq")
    assert res_dlq.status_code == 200
    assert res_dlq.json["count"] == 0

    # 3. Replay non-existent message returns 400
    res_replay = client.post("/api/v1/broker/dlq/missing-id/replay")
    assert res_replay.status_code == 400

    # 4. Clear DLQ
    res_clear = client.delete("/api/v1/broker/dlq")
    assert res_clear.status_code == 200
    assert res_clear.json["status"] == "CLEARED"
