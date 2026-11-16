"""Martin Fowler Circuit Breaker pattern implementation for PulseMesh."""

import threading
import time
from enum import Enum
from typing import Any, Callable, Optional


class CircuitState(str, Enum):
    """Enumeration of circuit breaker operational states."""

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreakerOpenException(Exception):
    """Raised when an execution is attempted on an open circuit breaker."""

    def __init__(self, service_name: str, recovery_remaining: float):
        self.service_name = service_name
        self.recovery_remaining = round(recovery_remaining, 2)
        super().__init__(
            f"Circuit breaker for service '{service_name}' is OPEN. "
            f"Cooldown active for {self.recovery_remaining}s."
        )


class CircuitBreaker:
    """Thread-safe circuit breaker protecting services from cascading failures."""

    def __init__(
        self,
        service_name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 10.0,
        half_open_max_trials: int = 2,
    ):
        self.service_name = service_name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_trials = half_open_max_trials

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._consecutive_successes = 0
        self._last_failure_time: Optional[float] = None
        self._lock = threading.RLock()

    @property
    def state(self) -> CircuitState:
        """Current operational state of the circuit breaker."""
        with self._lock:
            if self._state == CircuitState.OPEN and self._last_failure_time is not None:
                elapsed = time.time() - self._last_failure_time
                if elapsed >= self.recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                    self._consecutive_successes = 0
            return self._state

    @property
    def failure_count(self) -> int:
        """Current count of recorded failures in the active window."""
        with self._lock:
            return self._failure_count

    @property
    def consecutive_successes(self) -> int:
        """Count of successful trial executions while in HALF_OPEN state."""
        with self._lock:
            return self._consecutive_successes

    def can_execute(self) -> bool:
        """Check whether a request is permitted to execute through the breaker."""
        with self._lock:
            curr_state = self.state
            if curr_state in (CircuitState.CLOSED, CircuitState.HALF_OPEN):
                return True
            return False

    def record_success(self) -> None:
        """Record a successful request execution."""
        with self._lock:
            curr_state = self.state
            if curr_state == CircuitState.HALF_OPEN:
                self._consecutive_successes += 1
                if self._consecutive_successes >= self.half_open_max_trials:
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    self._consecutive_successes = 0
                    self._last_failure_time = None
            elif curr_state == CircuitState.CLOSED:
                self._failure_count = 0

    def record_failure(self) -> None:
        """Record an execution failure or connection error."""
        with self._lock:
            now = time.time()
            self._last_failure_time = now
            curr_state = self.state

            if curr_state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                self._failure_count = self.failure_threshold
                self._consecutive_successes = 0
            elif curr_state == CircuitState.CLOSED:
                self._failure_count += 1
                if self._failure_count >= self.failure_threshold:
                    self._state = CircuitState.OPEN

    def call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute a callable wrapped in circuit breaker protection."""
        with self._lock:
            if not self.can_execute():
                remaining = 0.0
                if self._last_failure_time is not None:
                    elapsed = time.time() - self._last_failure_time
                    remaining = max(0.0, self.recovery_timeout - elapsed)
                raise CircuitBreakerOpenException(self.service_name, remaining)

        try:
            result = func(*args, **kwargs)
            self.record_success()
            return result
        except Exception:
            self.record_failure()
            raise

    def reset(self) -> None:
        """Manually reset the circuit breaker back to healthy CLOSED state."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._consecutive_successes = 0
            self._last_failure_time = None

    def trip(self) -> None:
        """Manually trip the circuit breaker into OPEN state for chaos testing."""
        with self._lock:
            self._state = CircuitState.OPEN
            self._failure_count = self.failure_threshold
            self._last_failure_time = time.time()
            self._consecutive_successes = 0

    def get_status(self) -> dict[str, Any]:
        """Return a snapshot of current circuit breaker metrics."""
        with self._lock:
            curr_state = self.state
            remaining = 0.0
            if curr_state == CircuitState.OPEN and self._last_failure_time is not None:
                elapsed = time.time() - self._last_failure_time
                remaining = max(0.0, self.recovery_timeout - elapsed)

            return {
                "service_name": self.service_name,
                "state": curr_state.value,
                "failure_count": self._failure_count,
                "consecutive_successes": self._consecutive_successes,
                "failure_threshold": self.failure_threshold,
                "recovery_timeout": self.recovery_timeout,
                "half_open_max_trials": self.half_open_max_trials,
                "cooldown_remaining_seconds": round(remaining, 2),
            }


class CircuitBreakerRegistry:
    """Thread-safe registry managing named circuit breakers across services."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._breakers: dict[str, CircuitBreaker] = {}

    def get(
        self,
        service_name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 10.0,
        half_open_max_trials: int = 2,
    ) -> CircuitBreaker:
        """Retrieve existing or construct a new CircuitBreaker for a service."""
        key = service_name.strip().lower()
        with self._lock:
            if key not in self._breakers:
                self._breakers[key] = CircuitBreaker(
                    service_name=key,
                    failure_threshold=failure_threshold,
                    recovery_timeout=recovery_timeout,
                    half_open_max_trials=half_open_max_trials,
                )
            return self._breakers[key]

    def get_all_statuses(self) -> dict[str, dict[str, Any]]:
        """Return metrics snapshots for all registered circuit breakers."""
        with self._lock:
            return {name: cb.get_status() for name, cb in self._breakers.items()}

    def reset_all(self) -> None:
        """Reset all circuit breakers in the registry to CLOSED state."""
        with self._lock:
            for cb in self._breakers.values():
                cb.reset()

    def clear(self) -> None:
        """Clear all registered circuit breakers."""
        with self._lock:
            self._breakers.clear()
