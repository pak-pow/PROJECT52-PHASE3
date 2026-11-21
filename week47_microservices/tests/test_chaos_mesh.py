"""End-to-End Microservices Chaos and Concurrency Test Suite for PulseMesh.

Validates resilience patterns under active chaos:
- Node failure during active traffic and zero-downtime failover to healthy replicas.
- High-contention concurrent stock reservations with race condition safety.
- Circuit breaker trip and self-healing under simulated cascading outages.
- Dead-Letter Queue (DLQ) quarantine and replay of poison messages.
- Resilient client retry with backoff on transient network faults.
- Gateway rate limiter defense under high-velocity traffic spikes.
"""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import MagicMock

from gateway.app import create_gateway_app
from gateway.proxy import ReverseProxyRouter
from gateway.rate_limiter import GatewayRateLimiter
from services.catalog.app import create_catalog_app
from services.registry.instance_store import InstanceStore
from shared.circuit_breaker import (
    CircuitBreakerOpenException,
    CircuitBreakerRegistry,
    CircuitState,
)
from shared.client import PulseClient, PulseResponse
from shared.message_broker import CloudEvent, MessageBroker
from shared.models import HealthStatus, ServiceInstance


def test_chaos_node_failover_during_active_traffic():
    """Verify traffic seamlessly redirects to healthy replica when a node dies."""
    store = InstanceStore()

    node_1 = ServiceInstance(
        service_name="catalog-service",
        instance_id="catalog-8003",
        host="127.0.0.1",
        port=8003,
        health_status=HealthStatus.HEALTHY,
    )
    node_2 = ServiceInstance(
        service_name="catalog-service",
        instance_id="catalog-8013",
        host="127.0.0.1",
        port=8013,
        health_status=HealthStatus.HEALTHY,
    )
    store.register(node_1)
    store.register(node_2)

    call_log = []

    def mock_request(service_name, method, path, **kwargs):
        instances = store.get_instances(service_name=service_name, healthy_only=True)
        if not instances:
            raise RuntimeError("No healthy instances available")
        # Route to first healthy instance in current list
        chosen = instances[0]
        call_log.append(chosen.instance_id)
        return PulseResponse(
            status_code=200,
            headers={"Content-Type": "application/json"},
            data={"status": "OK", "instance": chosen.instance_id},
            raw_text="",
            latency_ms=12.5,
            instance_id=chosen.instance_id,
            service_name=service_name,
        )

    client = MagicMock(spec=PulseClient)
    client.request.side_effect = mock_request

    router = ReverseProxyRouter(pulse_client=client)

    # 1. Dispatch while both nodes are alive
    status, _, data, _ = router.forward_request("GET", "/api/v1/products")
    assert status == 200

    # 2. Inject chaos: node_1 experiences catastrophic failure
    node_1_inst = store.get_instance("catalog-8003")
    assert node_1_inst is not None
    node_1_inst.health_status = HealthStatus.DOWN

    # 3. Subsequent requests route strictly to node_2 with zero client errors
    for _ in range(5):
        status, _, data, meta = router.forward_request("GET", "/api/v1/products")
        assert status == 200
        assert data["instance"] == "catalog-8013"

    # 4. Self-healing: node_1 recovers
    node_1_inst.health_status = HealthStatus.HEALTHY
    healthy = store.get_instances("catalog-service", healthy_only=True)
    assert len(healthy) == 2


def test_chaos_concurrent_stock_reservations_no_overselling():
    """Verify zero overselling when multiple threads compete for limited stock."""
    app = create_catalog_app(db_path=":memory:")
    client = app.test_client()

    # Create product with initial inventory of 5 units
    prod_res = client.post(
        "/api/v1/products",
        json={
            "sku": "CHAOS-SKU-99",
            "name": "Limited Edition Mesh Token",
            "price_cents": 5000,
            "stock_quantity": 5,
        },
    )
    assert prod_res.status_code == 201
    product_id = prod_res.json["id"]

    # 20 concurrent threads attempt to reserve 1 unit each
    total_workers = 20
    results = []

    def attempt_reservation(worker_idx: int):
        thread_client = app.test_client()
        order_id = f"ord_chaos_worker_{worker_idx}"
        resp = thread_client.post(
            "/api/v1/inventory/reserve",
            json={
                "order_id": order_id,
                "items": [{"product_id": product_id, "quantity": 1}],
            },
        )
        return resp.status_code

    with ThreadPoolExecutor(max_workers=total_workers) as executor:
        futures = [
            executor.submit(attempt_reservation, i) for i in range(total_workers)
        ]
        for f in as_completed(futures):
            results.append(f.result())

    # Exactly 5 must succeed (200 or 201), exactly 15 must fail (400)
    successes = [code for code in results if code in (200, 201)]
    failures = [code for code in results if code == 400]

    assert len(successes) == 5
    assert len(failures) == 15

    # Check product available stock is 0
    final_prod = client.get(f"/api/v1/products/{product_id}")
    assert final_prod.status_code == 200
    assert final_prod.json["stock_quantity"] == 5
    assert final_prod.json["available_stock"] == 0


def test_chaos_circuit_breaker_cascading_failure_isolation():
    """Verify failure in one service trips its breaker without affecting others."""
    cb_registry = CircuitBreakerRegistry()
    cb_order = cb_registry.get(
        "order-service", failure_threshold=3, recovery_timeout=0.5
    )
    cb_catalog = cb_registry.get(
        "catalog-service", failure_threshold=3, recovery_timeout=0.5
    )

    # Simulate 3 consecutive failures to order-service
    for _ in range(3):
        cb_order.record_failure()

    # Order service breaker is now OPEN
    assert cb_order.state == CircuitState.OPEN
    # Catalog service breaker is untouched and CLOSED
    assert cb_catalog.state == CircuitState.CLOSED

    # PulseClient executing request against order-service fails fast
    mock_store = InstanceStore()
    pulse = PulseClient(instance_store=mock_store, circuit_breaker_registry=cb_registry)

    # Order request raises CircuitBreakerOpenException immediately
    try:
        pulse.request("order-service", "GET", "/api/v1/orders")
        raise AssertionError("Expected CircuitBreakerOpenException")
    except CircuitBreakerOpenException as exc:
        assert exc.service_name == "order-service"
        assert exc.recovery_remaining >= 0.0

    # Catalog request does NOT raise CircuitBreakerOpenException
    mock_store.register(
        ServiceInstance(
            service_name="catalog-service",
            instance_id="c1",
            host="127.0.0.1",
            port=8003,
            health_status=HealthStatus.HEALTHY,
        )
    )

    # Mock the session to succeed for catalog
    mock_session = MagicMock()
    mock_http_resp = MagicMock()
    mock_http_resp.status_code = 200
    mock_http_resp.headers = {"Content-Type": "application/json"}
    mock_http_resp.json.return_value = {"products": []}
    mock_session.request.return_value = mock_http_resp
    pulse.session = mock_session

    cat_resp = pulse.request("catalog-service", "GET", "/api/v1/products")
    assert cat_resp.status_code == 200

    # Wait for cooldown and verify self-healing trial
    time.sleep(0.6)
    assert cb_order.state == CircuitState.HALF_OPEN
    cb_order.record_success()
    cb_order.record_success()
    assert cb_order.state == CircuitState.CLOSED


def test_chaos_poison_message_dlq_quarantine_and_replay():
    """Verify poison events are quarantined to DLQ and can be safely replayed."""
    broker = MessageBroker()
    topic = "orders.events"

    # Subscriber 1 crashes on all events
    def bad_subscriber(event: CloudEvent):
        raise ValueError("Fatal corrupt payload exception")

    broker.subscribe(topic, "chaos-consumer", bad_subscriber, max_retries=2)

    poison_event = CloudEvent(
        id="evt_poison_999",
        source="order-service",
        type="order.corrupt",
        data={"corrupted_field": True},
    )

    # Publish message - retry limit reached, message quarantined to DLQ
    broker.publish(topic, poison_event)

    dlq = broker.get_dlq()
    assert len(dlq) == 1
    dlq_id = dlq[0]["id"]
    assert dlq[0]["event"]["id"] == "evt_poison_999"
    assert dlq[0]["retry_count"] == 2
    assert "Fatal corrupt payload" in dlq[0]["error_reason"]

    # Now replace the consumer with a healthy handler and replay
    broker.unsubscribe(topic, "chaos-consumer")
    replayed_records = []

    def fixed_subscriber(event: CloudEvent):
        replayed_records.append(event.id)

    broker.subscribe(topic, "chaos-consumer", fixed_subscriber)

    # Replay DLQ event
    replayed = broker.replay_dlq(dlq_id)
    assert replayed is True
    assert len(replayed_records) == 1
    assert replayed_records[0] == "evt_poison_999"
    assert len(broker.get_dlq()) == 0


def test_chaos_gateway_rate_limiter_ddos_defense():
    """Verify high-concurrency client flood is throttled without hurting others."""
    limiter = GatewayRateLimiter(
        rate_per_second=5.0, burst_capacity=5.0, whitelist={"127.0.0.1"}
    )
    mock_pulse = MagicMock(spec=PulseClient)
    mock_pulse.request.return_value = PulseResponse(
        status_code=200,
        headers={"Content-Type": "application/json"},
        data={"items": []},
        raw_text="",
        latency_ms=5.0,
        instance_id="user-01",
        service_name="user-service",
    )
    app = create_gateway_app(rate_limiter=limiter, pulse_client=mock_pulse)
    client = app.test_client()

    attacker_ip = "198.51.100.42"
    statuses = []

    # Attacker fires 20 rapid requests through reverse proxy
    for _ in range(20):
        resp = client.get(
            "/api/v1/users",
            headers={"X-Forwarded-For": attacker_ip},
        )
        statuses.append(resp.status_code)

    # First 5 succeed, subsequent 15 receive 429
    successes = [s for s in statuses if s == 200]
    throttled = [s for s in statuses if s == 429]

    assert len(successes) == 5
    assert len(throttled) == 15

    # Meanwhile, whitelisted localhost traffic continues unaffected
    legit_resp = client.get(
        "/api/v1/users",
        headers={"X-Forwarded-For": "127.0.0.1"},
    )
    assert legit_resp.status_code == 200


def test_chaos_client_transient_failure_exponential_backoff():
    """Verify PulseClient recovers from transient failures using retry loops."""
    mock_session = MagicMock()
    # First 2 requests return 503 Server Error, 3rd returns 200 OK
    resp_503 = MagicMock()
    resp_503.status_code = 503
    resp_503.headers = {"Content-Type": "application/json"}
    resp_503.json.return_value = {"error": "Temporary upstream glitch"}

    resp_200 = MagicMock()
    resp_200.status_code = 200
    resp_200.headers = {"Content-Type": "application/json"}
    resp_200.json.return_value = {"user": {"id": "usr_recovered"}}

    mock_session.request.side_effect = [resp_503, resp_503, resp_200]

    store = InstanceStore()
    store.register(
        ServiceInstance(
            service_name="user-service",
            instance_id="usr-1",
            host="127.0.0.1",
            port=8002,
            health_status=HealthStatus.HEALTHY,
        )
    )

    pulse = PulseClient(
        instance_store=store,
        max_retries=3,
        retry_backoff_factor=0.01,
        session=mock_session,
    )

    # Request with max_retries=3 should survive the 2 transient glitches
    res = pulse.request(
        "user-service",
        "GET",
        "/api/v1/users/usr_recovered",
    )

    assert res.status_code == 200
    assert res.data["user"]["id"] == "usr_recovered"
    assert mock_session.request.call_count == 3
