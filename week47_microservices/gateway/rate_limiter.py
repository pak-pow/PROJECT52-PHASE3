"""Token bucket rate limiter protecting API Gateway against traffic spikes."""

import math
import threading
import time
from typing import Any, Optional


class TokenBucket:
    """Thread-safe single token bucket maintaining burst and sustained limits."""

    def __init__(self, capacity: float, refill_rate: float):
        self.capacity = float(capacity)
        self.refill_rate = float(refill_rate)
        self.tokens = float(capacity)
        self.last_refill = time.time()
        self.lock = threading.Lock()

    def consume(self, cost: float = 1.0) -> tuple[bool, int, float]:
        """Attempt to consume tokens.

        Returns:
            Tuple of (allowed, remaining_tokens, retry_after_seconds)
        """
        with self.lock:
            now = time.time()
            elapsed = max(0.0, now - self.last_refill)
            self.last_refill = now

            # Refill tokens up to maximum burst capacity
            self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)

            if self.tokens >= cost:
                self.tokens -= cost
                return True, int(self.tokens), 0.0

            # Calculate wait time until enough tokens are replenished
            needed = cost - self.tokens
            retry_after = math.ceil(needed / self.refill_rate)
            return False, 0, max(1.0, float(retry_after))


class GatewayRateLimiter:
    """Multi-client token bucket rate limiter with sliding replenishment."""

    def __init__(
        self,
        rate_per_second: float = 100.0,
        burst_capacity: float = 150.0,
        whitelist: Optional[set[str]] = None,
    ):
        self.rate_per_second = max(0.1, float(rate_per_second))
        self.burst_capacity = max(1.0, float(burst_capacity))
        self.whitelist = (
            whitelist if whitelist is not None else {"127.0.0.1", "localhost"}
        )
        self._buckets: dict[str, TokenBucket] = {}
        self._lock = threading.RLock()
        self._total_requests = 0
        self._rate_limited_requests = 0

    def check_rate_limit(self, client_key: str, cost: float = 1.0) -> dict[str, Any]:
        """Evaluate rate limit compliance for a client key."""
        clean_key = client_key.strip()

        with self._lock:
            self._total_requests += 1

            if clean_key in self.whitelist:
                return {
                    "allowed": True,
                    "limit": int(self.burst_capacity),
                    "remaining": int(self.burst_capacity),
                    "retry_after": 0,
                    "whitelisted": True,
                }

            if clean_key not in self._buckets:
                self._buckets[clean_key] = TokenBucket(
                    capacity=self.burst_capacity,
                    refill_rate=self.rate_per_second,
                )
            bucket = self._buckets[clean_key]

        allowed, remaining, retry_after = bucket.consume(cost)

        with self._lock:
            if not allowed:
                self._rate_limited_requests += 1

        return {
            "allowed": allowed,
            "limit": int(self.burst_capacity),
            "remaining": remaining,
            "retry_after": int(retry_after),
            "whitelisted": False,
        }

    def get_stats(self) -> dict[str, Any]:
        """Retrieve rate limiter utilization statistics."""
        with self._lock:
            active_clients = len(self._buckets)
            rejected = self._rate_limited_requests
            total = self._total_requests
            rejection_rate = round((rejected / total * 100.0) if total > 0 else 0.0, 2)

            return {
                "active_clients": active_clients,
                "total_requests": total,
                "rate_limited_requests": rejected,
                "rejection_rate_percent": rejection_rate,
                "rate_per_second": self.rate_per_second,
                "burst_capacity": self.burst_capacity,
            }

    def clear(self) -> None:
        """Purge all client token buckets and reset counters."""
        with self._lock:
            self._buckets.clear()
            self._total_requests = 0
            self._rate_limited_requests = 0
