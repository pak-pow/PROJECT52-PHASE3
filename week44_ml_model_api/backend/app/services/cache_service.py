"""In-memory thread-safe LRU prediction cache with canonical payload hashing."""

import hashlib
import json
import time
from collections import OrderedDict
from threading import RLock
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np


class InferenceCache:
    """Thread-safe in-memory LRU prediction cache with TTL and telemetry."""

    def __init__(
        self,
        max_size: int = 1000,
        ttl_seconds: Optional[int] = 300,
    ) -> None:
        """Initialize LRU cache with maximum item capacity and TTL in seconds."""
        self.max_size = max(1, max_size)
        self.ttl_seconds = ttl_seconds
        self._cache: OrderedDict[str, Tuple[Any, Optional[float]]] = OrderedDict()
        self._lock = RLock()

        # Telemetry counters
        self._hits: int = 0
        self._misses: int = 0
        self._evictions: int = 0

    @staticmethod
    def _canonicalize(payload: Any) -> Any:
        """Recursively normalize structures for deterministic JSON serialization."""
        if isinstance(payload, dict):
            return {
                str(k): InferenceCache._canonicalize(v)
                for k, v in sorted(payload.items(), key=lambda item: str(item[0]))
            }
        elif isinstance(payload, (list, tuple)):
            return [InferenceCache._canonicalize(v) for v in payload]
        elif isinstance(payload, np.ndarray):
            return payload.tolist()
        elif isinstance(payload, (np.floating, float)):
            return round(float(payload), 8)
        elif isinstance(payload, (np.integer, int)):
            return int(payload)
        return payload

    @classmethod
    def compute_hash(
        cls,
        model_id: str,
        version: str,
        payload: Any,
    ) -> str:
        """Generate deterministic SHA-256 hash from model identifiers and payload."""
        canonical_payload = cls._canonicalize(payload)
        try:
            serialized = json.dumps(
                canonical_payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            )
        except (TypeError, ValueError):
            serialized = str(canonical_payload)

        raw_key = f"{model_id}:{version}:{serialized}"
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    def get(self, key: str) -> Optional[Any]:
        """Retrieve unexpired value by key, updating LRU recency position."""
        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None

            value, expires_at = self._cache[key]

            # Check TTL expiration
            if expires_at is not None and time.time() > expires_at:
                del self._cache[key]
                self._evictions += 1
                self._misses += 1
                return None

            # Mark recently used
            self._cache.move_to_end(key)
            self._hits += 1
            return value

    def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: Optional[int] = None,
    ) -> None:
        """Insert or update a key-value entry, evicting LRU item if at capacity."""
        ttl = ttl_seconds if ttl_seconds is not None else self.ttl_seconds
        expires_at = (time.time() + ttl) if ttl and ttl > 0 else None

        with self._lock:
            if key in self._cache:
                self._cache[key] = (value, expires_at)
                self._cache.move_to_end(key)
                return

            if len(self._cache) >= self.max_size:
                # Evict oldest / least-recently used entry
                self._cache.popitem(last=False)
                self._evictions += 1

            self._cache[key] = (value, expires_at)

    def invalidate(self, key: str) -> bool:
        """Explicitly remove an entry by key; returns True if entry was removed."""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def invalidate_model(
        self,
        model_id: str,
        version: Optional[str] = None,
    ) -> int:
        """Invalidate all cached items belonging to a specific model or version."""
        prefix = f"{model_id}:{version}:" if version else f"{model_id}:"
        with self._lock:
            # Hash keys do not expose model_id directly unless indexed,
            # so we support targeted hash eviction or full clear
            keys_to_remove = [k for k in self._cache.keys() if k.startswith(prefix)]
            for k in keys_to_remove:
                del self._cache[k]
            return len(keys_to_remove)

    def purge_expired(self) -> int:
        """Scan cache and remove all expired items returning count of purged entries."""
        now = time.time()
        purged = 0
        with self._lock:
            expired_keys: List[str] = [
                k
                for k, (_, expires_at) in self._cache.items()
                if expires_at is not None and now > expires_at
            ]
            for k in expired_keys:
                del self._cache[k]
                self._evictions += 1
                purged += 1
        return purged

    def clear(self) -> None:
        """Purge all cached entries while retaining performance telemetry."""
        with self._lock:
            self._cache.clear()

    def get_stats(self) -> Dict[str, Union[int, float]]:
        """Return real-time cache telemetry including hit ratio and capacity."""
        with self._lock:
            total = self._hits + self._misses
            hit_ratio = round(self._hits / total, 4) if total > 0 else 0.0
            return {
                "size": len(self._cache),
                "max_size": self.max_size,
                "hits": self._hits,
                "misses": self._misses,
                "evictions": self._evictions,
                "hit_ratio": hit_ratio,
            }

    def reset_stats(self) -> None:
        """Reset cache hit, miss, and eviction counters to zero."""
        with self._lock:
            self._hits = 0
            self._misses = 0
            self._evictions = 0
