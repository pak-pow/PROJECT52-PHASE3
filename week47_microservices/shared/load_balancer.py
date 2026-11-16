"""Multi-strategy load balancing engine for PulseMesh microservices."""

import random
import threading
from contextlib import contextmanager
from enum import Enum
from typing import Any, Generator, Optional

from shared.circuit_breaker import CircuitBreakerRegistry, CircuitState
from shared.models import HealthStatus, ServiceInstance


class LoadBalancerStrategy(str, Enum):
    """Supported load balancing distribution algorithms."""

    ROUND_ROBIN = "ROUND_ROBIN"
    LEAST_CONNECTIONS = "LEAST_CONNECTIONS"
    LATENCY_WEIGHTED = "LATENCY_WEIGHTED"
    RANDOM = "RANDOM"


class RoundRobinStrategy:
    """Sequential cyclic load balancing algorithm."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._indices: dict[str, int] = {}

    def select(
        self, instances: list[ServiceInstance], service_name: str
    ) -> Optional[ServiceInstance]:
        """Select next instance in cyclic round-robin sequence."""
        if not instances:
            return None
        with self._lock:
            idx = self._indices.get(service_name, 0)
            selected = instances[idx % len(instances)]
            self._indices[service_name] = (idx + 1) % len(instances)
            return selected


class LeastConnectionsStrategy:
    """Routes incoming requests to the instance with fewest active connections."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._active_conns: dict[str, int] = {}

    def increment(self, instance_id: str) -> None:
        """Increment active concurrent connection counter for an instance."""
        with self._lock:
            self._active_conns[instance_id] = self._active_conns.get(instance_id, 0) + 1

    def decrement(self, instance_id: str) -> None:
        """Decrement active connection counter, keeping minimum at zero."""
        with self._lock:
            val = self._active_conns.get(instance_id, 0)
            self._active_conns[instance_id] = max(0, val - 1)

    def get_connections(self, instance_id: str) -> int:
        """Return active connection count for an instance."""
        with self._lock:
            return self._active_conns.get(instance_id, 0)

    def select(
        self, instances: list[ServiceInstance], service_name: str
    ) -> Optional[ServiceInstance]:
        """Select instance with minimal active concurrent connections."""
        if not instances:
            return None
        with self._lock:
            # Sort instances by active connections ascending
            return min(
                instances,
                key=lambda inst: self._active_conns.get(inst.instance_id, 0),
            )


class LatencyWeightedStrategy:
    """Favors instances demonstrating the lowest moving-average latency."""

    def __init__(self, sample_limit: int = 20, default_latency_ms: float = 20.0):
        self.sample_limit = sample_limit
        self.default_latency_ms = default_latency_ms
        self._lock = threading.RLock()
        self._latencies: dict[str, list[float]] = {}

    def record_latency(self, instance_id: str, latency_ms: float) -> None:
        """Record an observed execution duration for an instance."""
        with self._lock:
            samples = self._latencies.setdefault(instance_id, [])
            samples.append(latency_ms)
            if len(samples) > self.sample_limit:
                samples.pop(0)

    def get_average_latency(self, instance_id: str) -> float:
        """Calculate moving-average latency in milliseconds for an instance."""
        with self._lock:
            samples = self._latencies.get(instance_id)
            if not samples:
                return self.default_latency_ms
            return sum(samples) / len(samples)

    def select(
        self, instances: list[ServiceInstance], service_name: str
    ) -> Optional[ServiceInstance]:
        """Select instance with lowest moving average response latency."""
        if not instances:
            return None
        with self._lock:
            return min(
                instances,
                key=lambda inst: self.get_average_latency(inst.instance_id),
            )


class RandomStrategy:
    """Uniform pseudorandom distribution algorithm."""

    def select(
        self, instances: list[ServiceInstance], service_name: str
    ) -> Optional[ServiceInstance]:
        """Select an instance uniformly at random."""
        if not instances:
            return None
        return random.choice(instances)  # nosec B311


class LoadBalancer:
    """Composite load balancer managing strategies and circuit breaker filtering."""

    def __init__(
        self,
        default_strategy: LoadBalancerStrategy = LoadBalancerStrategy.ROUND_ROBIN,
        circuit_breaker_registry: Optional[CircuitBreakerRegistry] = None,
    ):
        self.default_strategy = default_strategy
        self.circuit_breaker_registry = circuit_breaker_registry

        self.round_robin = RoundRobinStrategy()
        self.least_connections = LeastConnectionsStrategy()
        self.latency_weighted = LatencyWeightedStrategy()
        self.random = RandomStrategy()

    def choose(
        self,
        service_name: str,
        instances: list[ServiceInstance],
        strategy: Optional[LoadBalancerStrategy] = None,
    ) -> Optional[ServiceInstance]:
        """Choose best instance using selected strategy and circuit protection."""
        if not instances:
            return None

        # Filter out instances whose service circuit breaker is open
        eligible = instances
        if self.circuit_breaker_registry is not None:
            cb = self.circuit_breaker_registry.get(service_name)
            if cb.state == CircuitState.OPEN:
                # If breaker is open, fail fast
                return None

        # Prefer HEALTHY instances over degraded ones
        healthy_candidates = [
            inst for inst in eligible if inst.health_status == HealthStatus.HEALTHY
        ]
        candidates = healthy_candidates if healthy_candidates else eligible

        active_strategy = strategy or self.default_strategy
        if active_strategy == LoadBalancerStrategy.ROUND_ROBIN:
            return self.round_robin.select(candidates, service_name)
        elif active_strategy == LoadBalancerStrategy.LEAST_CONNECTIONS:
            return self.least_connections.select(candidates, service_name)
        elif active_strategy == LoadBalancerStrategy.LATENCY_WEIGHTED:
            return self.latency_weighted.select(candidates, service_name)
        elif active_strategy == LoadBalancerStrategy.RANDOM:
            return self.random.select(candidates, service_name)
        return self.round_robin.select(candidates, service_name)

    @contextmanager
    def track_connection(self, instance_id: str) -> Generator[None, None, None]:
        """Context manager tracking in-flight connection for least-connections LB."""
        self.least_connections.increment(instance_id)
        try:
            yield
        finally:
            self.least_connections.decrement(instance_id)

    def record_latency(self, instance_id: str, latency_ms: float) -> None:
        """Record response latency for latency-weighted load balancing."""
        self.latency_weighted.record_latency(instance_id, latency_ms)

    def get_metrics(self) -> dict[str, Any]:
        """Return load balancer metrics snapshot."""
        return {
            "default_strategy": self.default_strategy.value,
            "active_connections": dict(self.least_connections._active_conns),
            "average_latencies": {
                inst_id: self.latency_weighted.get_average_latency(inst_id)
                for inst_id in self.latency_weighted._latencies
            },
        }
