"""Sliding-window latency telemetry and performance metrics engine for PulseInfer."""

import threading
import time
from collections import deque
from typing import Any, Deque, Dict, List, Tuple

import numpy as np


class TelemetryEngine:
    """Computes exact latency percentiles and real-time inference telemetry."""

    def __init__(self, window_size: int = 500) -> None:
        """Initialize telemetry engine with maximum sliding window size."""
        self.window_size = max(1, window_size)
        self._lock = threading.Lock()

        # Global counters
        self._total_requests: int = 0
        self._successful_requests: int = 0
        self._failed_requests: int = 0
        self._cache_hits: int = 0

        # Global sliding window: (timestamp, latency_ms, cached, status)
        self._global_latencies: Deque[Tuple[float, float, bool, str]] = deque(
            maxlen=self.window_size
        )

        # Per-model metrics and sliding windows
        self._model_windows: Dict[str, Deque[Tuple[float, float, bool, str]]] = {}
        self._model_counters: Dict[str, Dict[str, int]] = {}

    def record(
        self,
        model_id: str,
        version: str,
        latency_ms: float,
        cached: bool = False,
        status: str = "success",
        batch_size: int = 1,
    ) -> None:
        """Record an inference execution event with latency and status flags."""
        now = time.perf_counter()
        clean_model = model_id.strip().lower()
        clean_status = status.strip().lower()

        with self._lock:
            # Update global counters
            self._total_requests += batch_size
            if clean_status == "success":
                self._successful_requests += batch_size
            else:
                self._failed_requests += batch_size

            if cached:
                self._cache_hits += batch_size

            entry = (now, max(0.0, float(latency_ms)), cached, clean_status)
            self._global_latencies.append(entry)

            # Update per-model state
            if clean_model not in self._model_windows:
                self._model_windows[clean_model] = deque(maxlen=self.window_size)
                self._model_counters[clean_model] = {
                    "total": 0,
                    "success": 0,
                    "failed": 0,
                    "cache_hits": 0,
                }

            self._model_windows[clean_model].append(entry)
            counters = self._model_counters[clean_model]
            counters["total"] += batch_size
            if clean_status == "success":
                counters["success"] += batch_size
            else:
                counters["failed"] += batch_size
            if cached:
                counters["cache_hits"] += batch_size

    def _compute_percentiles(self, latencies: List[float]) -> Dict[str, float]:
        """Calculate statistical percentiles over a given latency collection."""
        if not latencies:
            return {
                "p50": 0.0,
                "p90": 0.0,
                "p95": 0.0,
                "p99": 0.0,
                "min": 0.0,
                "max": 0.0,
                "avg": 0.0,
            }

        arr = np.array(latencies, dtype=np.float64)
        return {
            "p50": float(np.round(np.percentile(arr, 50), 3)),
            "p90": float(np.round(np.percentile(arr, 90), 3)),
            "p95": float(np.round(np.percentile(arr, 95), 3)),
            "p99": float(np.round(np.percentile(arr, 99), 3)),
            "min": float(np.round(np.min(arr), 3)),
            "max": float(np.round(np.max(arr), 3)),
            "avg": float(np.round(np.mean(arr), 3)),
        }

    def get_global_metrics(self) -> Dict[str, Any]:
        """Compute aggregated metrics across all active models and requests."""
        with self._lock:
            total = self._total_requests
            success = self._successful_requests
            failed = self._failed_requests
            hits = self._cache_hits

            latencies = [entry[1] for entry in self._global_latencies]
            percentiles = self._compute_percentiles(latencies)

            error_rate = round(failed / total, 4) if total > 0 else 0.0
            hit_ratio = round(hits / total, 4) if total > 0 else 0.0

            # Estimate throughput over window duration
            rps = 0.0
            if len(self._global_latencies) >= 2:
                time_span = self._global_latencies[-1][0] - self._global_latencies[0][0]
                if time_span > 0:
                    rps = round(len(self._global_latencies) / time_span, 2)

            return {
                "total_requests": total,
                "successful_requests": success,
                "failed_requests": failed,
                "cache_hits": hits,
                "cache_hit_ratio": hit_ratio,
                "error_rate": error_rate,
                "window_samples": len(self._global_latencies),
                "throughput_rps": rps,
                "latencies": percentiles,
            }

    def get_model_metrics(self, model_id: str) -> Dict[str, Any]:
        """Compute metrics specific to an individual model identifier."""
        clean_model = model_id.strip().lower()
        with self._lock:
            counters = self._model_counters.get(
                clean_model,
                {"total": 0, "success": 0, "failed": 0, "cache_hits": 0},
            )
            window = self._model_windows.get(clean_model, deque())

            total = counters["total"]
            failed = counters["failed"]
            hits = counters["cache_hits"]

            latencies = [entry[1] for entry in window]
            percentiles = self._compute_percentiles(latencies)

            error_rate = round(failed / total, 4) if total > 0 else 0.0
            hit_ratio = round(hits / total, 4) if total > 0 else 0.0

            return {
                "model_id": clean_model,
                "total_requests": total,
                "successful_requests": counters["success"],
                "failed_requests": failed,
                "cache_hits": hits,
                "cache_hit_ratio": hit_ratio,
                "error_rate": error_rate,
                "window_samples": len(window),
                "latencies": percentiles,
            }

    def get_all_models_metrics(self) -> Dict[str, Dict[str, Any]]:
        """Return metrics breakdown mapped by individual model identifiers."""
        with self._lock:
            models = list(self._model_counters.keys())
        return {m: self.get_model_metrics(m) for m in models}

    def reset(self) -> None:
        """Reset all counters, sliding windows, and historical percentiles."""
        with self._lock:
            self._total_requests = 0
            self._successful_requests = 0
            self._failed_requests = 0
            self._cache_hits = 0
            self._global_latencies.clear()
            self._model_windows.clear()
            self._model_counters.clear()
