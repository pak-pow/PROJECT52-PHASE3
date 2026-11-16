"""Unit tests for Martin Fowler Circuit Breaker state machine."""

import time

import pytest

from shared.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenException,
    CircuitBreakerRegistry,
    CircuitState,
)


def test_circuit_breaker_initial_state() -> None:
    """Verify circuit breaker initializes in CLOSED state with zero errors."""
    cb = CircuitBreaker("user-service", failure_threshold=3, recovery_timeout=0.2)
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 0
    assert cb.can_execute() is True

    status = cb.get_status()
    assert status["service_name"] == "user-service"
    assert status["state"] == "CLOSED"
    assert status["failure_count"] == 0


def test_circuit_breaker_trips_to_open() -> None:
    """Verify reaching failure threshold transitions circuit breaker to OPEN."""
    cb = CircuitBreaker("catalog-service", failure_threshold=3, recovery_timeout=0.2)

    cb.record_failure()
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 1

    cb.record_failure()
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 2

    # Third failure reaches threshold of 3 -> trips to OPEN
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    assert cb.failure_count == 3
    assert cb.can_execute() is False

    # Calling during OPEN raises CircuitBreakerOpenException
    with pytest.raises(CircuitBreakerOpenException) as exc_info:
        cb.call(lambda: "never called")
    assert "catalog-service" in str(exc_info.value)
    assert exc_info.value.recovery_remaining >= 0


def test_circuit_breaker_recovery_to_half_open_and_closed() -> None:
    """Verify recovery timeout transition to HALF_OPEN and healing to CLOSED."""
    cb = CircuitBreaker(
        "order-service",
        failure_threshold=2,
        recovery_timeout=0.1,
        half_open_max_trials=2,
    )

    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.OPEN

    # Wait for recovery cooldown
    time.sleep(0.15)
    assert cb.state == CircuitState.HALF_OPEN
    assert cb.can_execute() is True

    # First successful trial in HALF_OPEN
    cb.record_success()
    assert cb.state == CircuitState.HALF_OPEN
    assert cb.consecutive_successes == 1

    # Second successful trial reaches threshold of 2 -> heals back to CLOSED
    cb.record_success()
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 0
    assert cb.consecutive_successes == 0


def test_circuit_breaker_half_open_failure_re_trips() -> None:
    """Verify failure during HALF_OPEN immediately re-trips back to OPEN."""
    cb = CircuitBreaker(
        "payment-service",
        failure_threshold=2,
        recovery_timeout=0.1,
        half_open_max_trials=2,
    )

    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.OPEN

    time.sleep(0.15)
    assert cb.state == CircuitState.HALF_OPEN

    # Failure during trial -> immediate re-trip to OPEN
    cb.record_failure()
    assert cb.state == CircuitState.OPEN


def test_circuit_breaker_call_wrapper() -> None:
    """Verify call() wraps execution, records successes, and handles exceptions."""
    cb = CircuitBreaker("math-service", failure_threshold=2, recovery_timeout=0.5)

    def divide(a: int, b: int) -> float:
        return a / b

    # Success
    res = cb.call(divide, 10, 2)
    assert res == 5.0
    assert cb.state == CircuitState.CLOSED

    # Failure
    with pytest.raises(ZeroDivisionError):
        cb.call(divide, 10, 0)
    assert cb.failure_count == 1


def test_circuit_breaker_manual_trip_and_reset() -> None:
    """Verify manual trip and reset controls."""
    cb = CircuitBreaker("test-service")
    assert cb.state == CircuitState.CLOSED

    cb.trip()
    assert cb.state == CircuitState.OPEN

    cb.reset()
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 0


def test_circuit_breaker_registry() -> None:
    """Verify CircuitBreakerRegistry singleton behaviors."""
    registry = CircuitBreakerRegistry()
    cb1 = registry.get("auth-service", failure_threshold=4)
    cb2 = registry.get("auth-service")
    assert cb1 is cb2

    cb_other = registry.get("other-service")
    assert cb_other.service_name == "other-service"

    statuses = registry.get_all_statuses()
    assert "auth-service" in statuses
    assert "other-service" in statuses

    # Reset all
    cb1.trip()
    registry.reset_all()
    assert cb1.state == CircuitState.CLOSED

    # Clear registry
    registry.clear()
    assert len(registry.get_all_statuses()) == 0
