"""Unit tests for multi-strategy load balancer."""

from shared.circuit_breaker import CircuitBreakerRegistry
from shared.load_balancer import (
    LatencyWeightedStrategy,
    LeastConnectionsStrategy,
    LoadBalancer,
    LoadBalancerStrategy,
    RandomStrategy,
    RoundRobinStrategy,
)
from shared.models import HealthStatus, ServiceInstance


def make_instances() -> list[ServiceInstance]:
    """Helper creating three test ServiceInstance objects."""
    return [
        ServiceInstance(
            service_name="catalog-service",
            instance_id="catalog-01",
            host="127.0.0.1",
            port=8001,
        ),
        ServiceInstance(
            service_name="catalog-service",
            instance_id="catalog-02",
            host="127.0.0.1",
            port=8002,
        ),
        ServiceInstance(
            service_name="catalog-service",
            instance_id="catalog-03",
            host="127.0.0.1",
            port=8003,
        ),
    ]


def test_round_robin_strategy() -> None:
    """Verify RoundRobinStrategy distributes requests sequentially."""
    strategy = RoundRobinStrategy()
    instances = make_instances()

    first = strategy.select(instances, "catalog-service")
    second = strategy.select(instances, "catalog-service")
    third = strategy.select(instances, "catalog-service")
    fourth = strategy.select(instances, "catalog-service")

    assert first.instance_id == "catalog-01"
    assert second.instance_id == "catalog-02"
    assert third.instance_id == "catalog-03"
    assert fourth.instance_id == "catalog-01"

    # Empty list
    assert strategy.select([], "catalog-service") is None


def test_least_connections_strategy() -> None:
    """Verify LeastConnectionsStrategy selects instance with fewest active requests."""
    strategy = LeastConnectionsStrategy()
    instances = make_instances()

    # Initially all have 0 connections -> picks first
    selected = strategy.select(instances, "catalog-service")
    assert selected.instance_id == "catalog-01"

    # Increment connections on catalog-01 and catalog-02
    strategy.increment("catalog-01")
    strategy.increment("catalog-01")
    strategy.increment("catalog-02")

    # catalog-03 has 0 connections -> should be selected
    selected = strategy.select(instances, "catalog-service")
    assert selected.instance_id == "catalog-03"

    # Decrement catalog-01
    strategy.decrement("catalog-01")
    assert strategy.get_connections("catalog-01") == 1

    # Empty list
    assert strategy.select([], "catalog-service") is None


def test_latency_weighted_strategy() -> None:
    """Verify LatencyWeightedStrategy selects instance with lowest moving average."""
    strategy = LatencyWeightedStrategy(sample_limit=5, default_latency_ms=50.0)
    instances = make_instances()

    # Default latency when no samples recorded
    assert strategy.get_average_latency("unmeasured-01") == 50.0

    # Record latencies: catalog-01=100ms, catalog-02=15ms, catalog-03=60ms
    strategy.record_latency("catalog-01", 100.0)
    strategy.record_latency("catalog-02", 15.0)
    strategy.record_latency("catalog-03", 60.0)

    assert strategy.get_average_latency("catalog-01") == 100.0
    assert strategy.get_average_latency("catalog-02") == 15.0

    selected = strategy.select(instances, "catalog-service")
    assert selected.instance_id == "catalog-02"

    # Test exceeding sample limit to test pop(0)
    for i in range(10):
        strategy.record_latency("catalog-01", float(i * 10))
    assert len(strategy._latencies["catalog-01"]) == 5

    # Empty list
    assert strategy.select([], "catalog-service") is None


def test_random_strategy() -> None:
    """Verify RandomStrategy returns an instance from candidate list."""
    strategy = RandomStrategy()
    instances = make_instances()

    selected = strategy.select(instances, "catalog-service")
    assert selected is not None
    assert selected.instance_id in ["catalog-01", "catalog-02", "catalog-03"]

    assert strategy.select([], "catalog-service") is None


def test_composite_load_balancer() -> None:
    """Verify LoadBalancer orchestrates strategies and circuit breaker checks."""
    cb_registry = CircuitBreakerRegistry()
    lb = LoadBalancer(
        default_strategy=LoadBalancerStrategy.ROUND_ROBIN,
        circuit_breaker_registry=cb_registry,
    )
    instances = make_instances()

    # Round Robin selection
    first = lb.choose("catalog-service", instances)
    assert first.instance_id == "catalog-01"

    # Override with Least Connections
    lb.least_connections.increment("catalog-01")
    lb.least_connections.increment("catalog-02")
    chosen_lc = lb.choose(
        "catalog-service",
        instances,
        strategy=LoadBalancerStrategy.LEAST_CONNECTIONS,
    )
    assert chosen_lc.instance_id == "catalog-03"

    # Override with Latency Weighted
    lb.record_latency("catalog-01", 5.0)
    lb.record_latency("catalog-02", 50.0)
    chosen_lat = lb.choose(
        "catalog-service",
        instances,
        strategy=LoadBalancerStrategy.LATENCY_WEIGHTED,
    )
    assert chosen_lat.instance_id == "catalog-01"

    # Override with Random
    chosen_rand = lb.choose(
        "catalog-service",
        instances,
        strategy=LoadBalancerStrategy.RANDOM,
    )
    assert chosen_rand is not None

    # Context manager connection tracking
    with lb.track_connection("catalog-03"):
        assert lb.least_connections.get_connections("catalog-03") == 1
    assert lb.least_connections.get_connections("catalog-03") == 0

    # Metrics
    metrics = lb.get_metrics()
    assert metrics["default_strategy"] == "ROUND_ROBIN"
    assert "catalog-01" in metrics["average_latencies"]

    # When service circuit breaker is OPEN -> returns None
    cb = cb_registry.get("catalog-service")
    cb.trip()
    assert lb.choose("catalog-service", instances) is None

    # Empty instances list
    cb.reset()
    assert lb.choose("catalog-service", []) is None


def test_load_balancer_health_preference() -> None:
    """Verify LoadBalancer filters degraded instances when healthy nodes exist."""
    lb = LoadBalancer()
    healthy = ServiceInstance(
        service_name="auth-service",
        instance_id="auth-01",
        host="127.0.0.1",
        port=8001,
        health_status=HealthStatus.HEALTHY,
    )
    degraded1 = ServiceInstance(
        service_name="auth-service",
        instance_id="auth-02",
        host="127.0.0.1",
        port=8002,
        health_status=HealthStatus.DEGRADED,
    )
    degraded2 = ServiceInstance(
        service_name="auth-service",
        instance_id="auth-03",
        host="127.0.0.1",
        port=8003,
        health_status=HealthStatus.DEGRADED,
    )

    chosen = lb.choose("auth-service", [healthy, degraded1])
    assert chosen.instance_id == "auth-01"

    # If all instances are degraded, falls back to eligible list
    chosen_all_degraded = lb.choose("auth-service", [degraded1, degraded2])
    assert chosen_all_degraded is not None
