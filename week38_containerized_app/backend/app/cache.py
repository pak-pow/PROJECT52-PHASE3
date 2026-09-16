"""Cache abstraction layer supporting Redis and thread-safe in-memory fallback.

Provides deterministic get, set, delete, and health probes for Redis and in-memory
storage with TTL support and telemetry tracking (hits, misses, latency).
"""

import os
import threading
import time
from typing import Any, Dict, Optional

try:
    import redis

    HAS_REDIS = True
except ImportError:  # pragma: no cover
    HAS_REDIS = False


class InMemoryCache:
    """Thread-safe in-memory key-value cache with TTL expiration."""

    def __init__(self):
        self._store: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self.hits: int = 0
        self.misses: int = 0

    def get(self, key: str) -> Optional[str]:
        """Retrieve a value if not expired."""
        with self._lock:
            item = self._store.get(key)
            if item is None:
                self.misses += 1
                return None
            expiry = item.get("expires_at")
            if expiry and time.time() > expiry:
                del self._store[key]
                self.misses += 1
                return None
            self.hits += 1
            return item["value"]

    def set(self, key: str, value: str, ttl: Optional[int] = None) -> bool:
        """Store a value with optional TTL in seconds."""
        with self._lock:
            expires_at = time.time() + ttl if ttl else None
            self._store[key] = {"value": str(value), "expires_at": expires_at}
            return True

    def delete(self, key: str) -> bool:
        """Remove a key from the cache."""
        with self._lock:
            if key in self._store:
                del self._store[key]
                return True
            return False

    def clear(self) -> bool:
        """Purge all entries from the in-memory cache."""
        with self._lock:
            self._store.clear()
            self.hits = 0
            self.misses = 0
            return True

    def size(self) -> int:
        """Return count of active keys."""
        with self._lock:
            now = time.time()
            return sum(
                1
                for item in self._store.values()
                if not item.get("expires_at") or item["expires_at"] > now
            )


class CacheClient:
    """Unified cache interface resolving Redis or in-memory fallback."""

    def __init__(self, redis_url: Optional[str] = None):
        self.redis_url = (
            redis_url if redis_url is not None else os.getenv("REDIS_URL", "")
        )
        self._memory = InMemoryCache()
        self._redis_client = None
        self.engine = "in-memory"
        self._init_client()

    def _init_client(self) -> None:
        """Attempt connection to Redis if configured; fallback to in-memory."""
        if self.redis_url and HAS_REDIS:
            try:
                client = redis.from_url(
                    self.redis_url,
                    decode_responses=True,
                    socket_timeout=2.0,
                    socket_connect_timeout=2.0,
                )
                client.ping()
                self._redis_client = client
                self.engine = "redis"
            except Exception:
                self._redis_client = None
                self.engine = "in-memory"
        else:
            self._redis_client = None
            self.engine = "in-memory"

    def get(self, key: str) -> Optional[str]:
        """Fetch value from active cache engine."""
        if self._redis_client:
            try:
                return self._redis_client.get(key)
            except Exception:
                return self._memory.get(key)
        return self._memory.get(key)

    def set(self, key: str, value: str, ttl: Optional[int] = None) -> bool:
        """Store value with optional TTL in active cache engine."""
        if self._redis_client:
            try:
                if ttl:
                    return bool(self._redis_client.setex(key, ttl, str(value)))
                return bool(self._redis_client.set(key, str(value)))
            except Exception:
                return self._memory.set(key, value, ttl)
        return self._memory.set(key, value, ttl)

    def delete(self, key: str) -> bool:
        """Delete key from active cache engine."""
        if self._redis_client:
            try:
                return bool(self._redis_client.delete(key))
            except Exception:
                return self._memory.delete(key)
        return self._memory.delete(key)

    def clear(self) -> bool:
        """Clear cache entries in active engine."""
        if self._redis_client:
            try:
                return bool(self._redis_client.flushdb())
            except Exception:
                return self._memory.clear()
        return self._memory.clear()

    def check_health(self) -> Dict[str, Any]:
        """Measure cache responsiveness and latency in milliseconds."""
        start_time = time.perf_counter()
        try:
            if self._redis_client:
                self._redis_client.ping()
            else:
                self._memory.set("__health_probe__", "1", ttl=5)
                self._memory.get("__health_probe__")
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return {
                "status": "healthy",
                "engine": self.engine,
                "latency_ms": latency_ms,
            }
        except Exception as exc:
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return {
                "status": "unhealthy",
                "engine": self.engine,
                "latency_ms": latency_ms,
                "error": str(exc),
            }

    def get_stats(self) -> Dict[str, Any]:
        """Return cache engine statistics."""
        if self._redis_client:
            try:
                info = self._redis_client.info("stats")
                return {
                    "engine": "redis",
                    "hits": info.get("keyspace_hits", 0),
                    "misses": info.get("keyspace_misses", 0),
                }
            except Exception:
                pass
        return {
            "engine": "in-memory",
            "hits": self._memory.hits,
            "misses": self._memory.misses,
            "keys": self._memory.size(),
        }


# Global singleton client
cache = CacheClient()


def get_cache(redis_url: Optional[str] = None) -> CacheClient:
    """Return cache client instance (singleton if default, or custom instance)."""
    if redis_url is None:
        return cache
    return CacheClient(redis_url)
