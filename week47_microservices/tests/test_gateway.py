"""Unit and integration tests for API Gateway, Reverse Proxy, and Rate Limiter."""

import time
from unittest.mock import MagicMock

from gateway.app import create_gateway_app
from gateway.proxy import ReverseProxyRouter
from gateway.rate_limiter import GatewayRateLimiter, TokenBucket
from services.registry.instance_store import InstanceStore
from shared.circuit_breaker import CircuitBreakerOpenException
from shared.client import PulseClient, PulseResponse
from shared.models import HealthStatus, ServiceInstance

# ---------------------------------------------------------------------------
# Token Bucket & Rate Limiter Tests
# ---------------------------------------------------------------------------


def test_token_bucket_consume_and_refill():
    """Test token bucket initial consumption, depletion, and time refill."""
    bucket = TokenBucket(capacity=5.0, refill_rate=10.0)

    # 1. Consume 3 tokens
    allowed, remaining, retry_after = bucket.consume(3.0)
    assert allowed is True
    assert remaining == 2
    assert retry_after == 0.0

    # 2. Consume remaining 2 tokens
    allowed, remaining, _ = bucket.consume(2.0)
    assert allowed is True
    assert remaining == 0

    # 3. Next consumption fails
    allowed, remaining, retry_after = bucket.consume(1.0)
    assert allowed is False
    assert remaining == 0
    assert retry_after > 0.0

    # 4. Sleep briefly to replenish tokens
    time.sleep(0.2)  # Refills ~2 tokens at 10 tokens/sec
    allowed, remaining, _ = bucket.consume(1.0)
    assert allowed is True


def test_gateway_rate_limiter_whitelist_and_burst():
    """Test rate limiter whitelist bypass and burst limit exhaustion."""
    limiter = GatewayRateLimiter(
        rate_per_second=2.0,
        burst_capacity=3.0,
        whitelist={"10.0.0.1"},
    )

    # 1. Whitelisted IP is always permitted
    res = limiter.check_rate_limit("10.0.0.1")
    assert res["allowed"] is True
    assert res["whitelisted"] is True

    # 2. Non-whitelisted IP consumes burst capacity
    client_ip = "192.168.1.50"
    for _ in range(3):
        res = limiter.check_rate_limit(client_ip)
        assert res["allowed"] is True
        assert res["whitelisted"] is False

    # 4th request exceeds burst capacity
    res = limiter.check_rate_limit(client_ip)
    assert res["allowed"] is False
    assert res["remaining"] == 0
    assert res["retry_after"] >= 1

    # Check stats
    stats = limiter.get_stats()
    assert stats["total_requests"] == 5
    assert stats["rate_limited_requests"] == 1
    assert stats["rejection_rate_percent"] > 0.0

    # Clear stats
    limiter.clear()
    assert limiter.get_stats()["total_requests"] == 0


# ---------------------------------------------------------------------------
# Reverse Proxy Router Tests
# ---------------------------------------------------------------------------


def test_reverse_proxy_route_matching():
    """Test path matching and most-specific prefix resolution."""
    router = ReverseProxyRouter()

    # Exact prefix match
    matched = router.match_route("/api/v1/users")
    assert matched is not None
    assert matched[0] == "user-service"

    # Subpath match
    matched = router.match_route("/api/v1/users/usr_123/profile")
    assert matched is not None
    assert matched[0] == "user-service"
    assert matched[1] == "/api/v1/users/usr_123/profile"

    # Catalog and Order routes
    assert router.match_route("/api/v1/products")[0] == "catalog-service"
    assert router.match_route("/api/v1/orders/ord_99")[0] == "order-service"
    assert router.match_route("/api/v1/notifications")[0] == "notification-service"

    # Register custom route
    router.register_route("/api/v1/analytics", "analytics-service")
    assert router.match_route("/api/v1/analytics/dash")[0] == "analytics-service"

    # Unmatched route
    assert router.match_route("/api/v2/unknown") is None


def test_reverse_proxy_forward_unmatched_route():
    """Test proxy returns 404 when no service route matches."""
    router = ReverseProxyRouter()
    status, headers, body, _ = router.forward_request("GET", "/unknown/path")
    assert status == 404
    assert "No microservice route configured" in body["error"]


def test_reverse_proxy_forward_success():
    """Test proxy forwards request and sanitizes headers via PulseClient."""
    mock_client = MagicMock(spec=PulseClient)
    mock_client.request.return_value = PulseResponse(
        status_code=200,
        headers={"Content-Type": "application/json", "Connection": "close"},
        data={"user": {"id": "usr_test"}},
        raw_text="",
        latency_ms=12.5,
        instance_id="user-01",
        service_name="user-service",
    )

    router = ReverseProxyRouter(pulse_client=mock_client)
    status, headers, data, meta = router.forward_request(
        method="GET",
        path="/api/v1/users/usr_test",
        headers={"Authorization": "Bearer token", "Connection": "keep-alive"},
        correlation_id="corr_proxy_1",
    )

    assert status == 200
    assert data["user"]["id"] == "usr_test"
    assert headers["X-Correlation-ID"] == "corr_proxy_1"
    assert headers["X-Upstream-Service"] == "user-service"
    assert "Connection" not in headers  # Hop-by-hop header stripped
    assert meta["latency_ms"] >= 0.0

    # Check telemetry recorded
    stats = router.get_stats()
    assert "user-service" in stats["services"]
    assert stats["services"]["user-service"]["total_requests"] == 1


def test_reverse_proxy_circuit_breaker_open_handling():
    """Test proxy translates CircuitBreakerOpenException into HTTP 503."""
    mock_client = MagicMock(spec=PulseClient)
    mock_client.request.side_effect = CircuitBreakerOpenException(
        "catalog-service", 10.0
    )

    router = ReverseProxyRouter(pulse_client=mock_client)
    status, headers, body, meta = router.forward_request(
        method="GET",
        path="/api/v1/products",
        correlation_id="corr_cb_open",
    )

    assert status == 503
    assert "Circuit breaker is OPEN" in body["error"]
    assert headers["X-Correlation-ID"] == "corr_cb_open"
    assert meta["error"] == "CircuitBreakerOpen"


def test_reverse_proxy_upstream_error_handling():
    """Test proxy handles unexpected exceptions and returns HTTP 503."""
    mock_client = MagicMock(spec=PulseClient)
    mock_client.request.side_effect = RuntimeError("DNS resolution failed")

    router = ReverseProxyRouter(pulse_client=mock_client)
    status, headers, body, _ = router.forward_request(
        method="POST",
        path="/api/v1/orders",
    )

    assert status == 503
    assert "DNS resolution failed" in body["error"]


# ---------------------------------------------------------------------------
# API Gateway Flask Application Tests
# ---------------------------------------------------------------------------


def test_gateway_root_endpoint():
    """Test gateway root metadata endpoint."""
    app = create_gateway_app()
    client = app.test_client()

    res = client.get("/")
    assert res.status_code == 200
    assert res.json["service"] == "api-gateway"
    assert res.json["status"] == "OPERATIONAL"
    assert "/api/v1/users" in res.json["routes"]


def test_gateway_aggregated_health_probe():
    """Test aggregated health probe under various cluster health states."""
    store = InstanceStore()

    # Case 1: Populated store with all healthy instances
    store.register(
        ServiceInstance(
            service_name="user-service",
            instance_id="u1",
            host="127.0.0.1",
            port=8002,
            health_status=HealthStatus.HEALTHY,
        )
    )
    store.register(
        ServiceInstance(
            service_name="catalog-service",
            instance_id="c1",
            host="127.0.0.1",
            port=8003,
            health_status=HealthStatus.HEALTHY,
        )
    )

    app = create_gateway_app(instance_store=store)
    client = app.test_client()

    res = client.get("/health")
    assert res.status_code == 200
    assert res.json["status"] == "HEALTHY"
    assert res.json["services"]["user-service"]["status"] == "HEALTHY"

    # Case 2: Degraded instance in cluster
    store.register(
        ServiceInstance(
            service_name="order-service",
            instance_id="o1",
            host="127.0.0.1",
            port=8004,
            health_status=HealthStatus.DEGRADED,
        )
    )
    res_deg = client.get("/health")
    assert res_deg.status_code == 200
    assert res_deg.json["status"] == "DEGRADED"

    # Case 3: All registered services down
    store.clear()
    store.register(
        ServiceInstance(
            service_name="user-service",
            instance_id="u_down",
            host="127.0.0.1",
            port=8002,
            health_status=HealthStatus.DOWN,
        )
    )
    res_down = client.get("/health")
    assert res_down.status_code == 503
    assert res_down.json["status"] == "DOWN"


def test_gateway_stats_endpoint():
    """Test gateway stats endpoint reporting rate limiting and routing metrics."""
    app = create_gateway_app()
    client = app.test_client()

    res = client.get("/api/v1/gateway/stats")
    assert res.status_code == 200
    data = res.json
    assert data["service"] == "api-gateway"
    assert "rate_limiter" in data
    assert "routing" in data
    assert "circuit_breakers" in data


def test_gateway_reverse_proxy_dispatch():
    """Test dispatching requests through gateway to simulated backend service."""
    mock_pulse = MagicMock(spec=PulseClient)
    mock_pulse.request.return_value = PulseResponse(
        status_code=201,
        headers={"Content-Type": "application/json"},
        data={"order": {"id": "ord_gw_1", "status": "COMPLETED"}},
        raw_text="",
        latency_ms=18.0,
        instance_id="order-01",
        service_name="order-service",
    )

    app = create_gateway_app(pulse_client=mock_pulse)
    client = app.test_client()

    # Forward POST request through gateway
    res = client.post(
        "/api/v1/orders",
        json={"user_id": "usr_gw", "items": [{"sku": "SKU-1", "quantity": 1}]},
        headers={"X-Correlation-ID": "corr_e2e_1"},
    )

    assert res.status_code == 201
    assert res.json["order"]["id"] == "ord_gw_1"
    assert res.headers["X-Correlation-ID"] == "corr_e2e_1"
    assert "X-RateLimit-Limit" in res.headers
    assert "X-RateLimit-Remaining" in res.headers


def test_gateway_rate_limiting_enforcement():
    """Test gateway returns HTTP 429 when client exceeds rate limits."""
    # Configure tight limiter without localhost in whitelist
    tight_limiter = GatewayRateLimiter(
        rate_per_second=1.0,
        burst_capacity=2.0,
        whitelist=set(),
    )

    mock_pulse = MagicMock(spec=PulseClient)
    mock_pulse.request.return_value = PulseResponse(
        status_code=200,
        headers={},
        data={"status": "OK"},
        raw_text="",
        latency_ms=5.0,
        instance_id="u1",
        service_name="user-service",
    )

    app = create_gateway_app(pulse_client=mock_pulse, rate_limiter=tight_limiter)
    client = app.test_client()

    # 1. First 2 requests within burst capacity succeed
    assert client.get("/api/v1/users/u1").status_code == 200
    assert client.get("/api/v1/users/u1").status_code == 200

    # 2. 3rd request triggers 429 Too Many Requests
    res_blocked = client.get("/api/v1/users/u1")
    assert res_blocked.status_code == 429
    assert "Rate limit exceeded" in res_blocked.json["error"]
    assert "Retry-After" in res_blocked.headers
    assert res_blocked.headers["X-RateLimit-Remaining"] == "0"


def test_gateway_health_client_resolve_instances():
    """Test /health when instance_store is None and client resolves instances."""
    mock_pulse = MagicMock(spec=PulseClient)
    mock_pulse.resolve_instances.side_effect = [
        [
            ServiceInstance(
                service_name="user-service",
                instance_id="u1",
                host="127.0.0.1",
                port=8002,
                health_status=HealthStatus.HEALTHY,
            )
        ],
        RuntimeError("Registry connection error"),
        [],
        [],
        [],
    ]

    app = create_gateway_app(pulse_client=mock_pulse, instance_store=None)
    client = app.test_client()

    res = client.get("/health")
    assert res.status_code == 200
    assert res.json["services"]["user-service"]["status"] == "HEALTHY"


def test_gateway_non_json_response_dispatch():
    """Test gateway forward returning plain text response."""
    mock_pulse = MagicMock(spec=PulseClient)
    mock_pulse.request.return_value = PulseResponse(
        status_code=200,
        headers={"Content-Type": "text/plain"},
        data="raw plain text response",
        raw_text="raw plain text response",
        latency_ms=4.0,
        instance_id="u1",
        service_name="user-service",
    )

    app = create_gateway_app(pulse_client=mock_pulse)
    client = app.test_client()

    res = client.get("/api/v1/users/text")
    assert res.status_code == 200
    assert "raw plain text response" in res.data.decode("utf-8")


def test_gateway_partial_healthy_instances():
    """Test /health when a service has mixed healthy and degraded replicas."""
    store = InstanceStore()
    store.register(
        ServiceInstance(
            service_name="user-service",
            instance_id="u1",
            host="127.0.0.1",
            port=8002,
            health_status=HealthStatus.HEALTHY,
        )
    )
    store.register(
        ServiceInstance(
            service_name="user-service",
            instance_id="u2",
            host="127.0.0.1",
            port=8012,
            health_status=HealthStatus.DEGRADED,
        )
    )

    app = create_gateway_app(instance_store=store)
    client = app.test_client()

    res = client.get("/health")
    assert res.status_code == 200
    assert res.json["services"]["user-service"]["status"] == "DEGRADED"
    assert res.json["status"] == "DEGRADED"
