"""Dynamic request micro-batching service with worker thread pool execution."""

import threading
import time
from collections import deque
from typing import Any, Callable, Deque, Dict, List, Optional


class BatchItem:
    """Encapsulates a single inference request payload and resolution event."""

    def __init__(self, payload: Any, enqueue_time: float) -> None:
        """Initialize batch item with payload, timestamp, and synchronization event."""
        self.payload = payload
        self.enqueue_time = enqueue_time
        self.event = threading.Event()
        self.result: Any = None
        self.error: Optional[Exception] = None


class DynamicBatcher:
    """Asynchronous request micro-batcher grouping concurrent inference payloads."""

    def __init__(
        self,
        predict_fn: Callable[[List[Any]], List[Any]],
        max_batch_size: int = 32,
        timeout_ms: float = 10.0,
        name: str = "batcher",
    ) -> None:
        """Initialize dynamic batcher with callable, capacity, and timeout."""
        self.predict_fn = predict_fn
        self.max_batch_size = max(1, max_batch_size)
        self.timeout_ms = max(0.1, float(timeout_ms))
        self.name = name

        self._queue: Deque[BatchItem] = deque()
        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)
        self._running = False
        self._worker_thread: Optional[threading.Thread] = None

        # Telemetry metrics
        self._total_requests: int = 0
        self._total_batches: int = 0
        self._total_batch_size_sum: int = 0
        self._total_wait_time_ms: float = 0.0
        self._total_exec_time_ms: float = 0.0

    def start(self) -> None:
        """Start the background micro-batch worker thread."""
        with self._condition:
            if self._running:
                return
            self._running = True
            self._worker_thread = threading.Thread(
                target=self._worker_loop,
                name=f"DynamicBatcher-{self.name}",
                daemon=True,
            )
            self._worker_thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        """Stop worker thread and reject any remaining pending requests."""
        with self._condition:
            if not self._running:
                return
            self._running = False
            self._condition.notify_all()

        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=timeout)

        # Abort any lingering items with shutdown error
        with self._condition:
            while self._queue:
                item = self._queue.popleft()
                item.error = RuntimeError("Batcher stopped before execution")
                item.event.set()

    def submit(self, payload: Any, timeout: Optional[float] = None) -> Any:
        """Enqueue payload and block until batch prediction completes or times out."""
        now = time.perf_counter()
        item = BatchItem(payload=payload, enqueue_time=now)

        with self._condition:
            if not self._running:
                raise RuntimeError(f"DynamicBatcher '{self.name}' is not running")

            self._queue.append(item)
            # Wake up worker if batch capacity reached
            if len(self._queue) >= self.max_batch_size:
                self._condition.notify()
            else:
                self._condition.notify()

        # Wait for worker thread to process the batch
        completed = item.event.wait(timeout=timeout)
        if not completed:
            raise TimeoutError(
                f"Inference request in batcher '{self.name}' timed out after {timeout}s"
            )

        if item.error is not None:
            raise item.error

        return item.result

    def _worker_loop(self) -> None:
        """Continuous worker loop aggregating items into batches for execution."""
        while True:
            batch: List[BatchItem] = []

            with self._condition:
                # Wait while queue is empty and batcher is running
                while not self._queue and self._running:
                    self._condition.wait()

                if not self._running and not self._queue:
                    break

                # Wait until batch reaches capacity OR timeout expires
                while self._queue and self._running:
                    if len(self._queue) >= self.max_batch_size:
                        break

                    oldest = self._queue[0]
                    elapsed_sec = time.perf_counter() - oldest.enqueue_time
                    remaining_sec = (self.timeout_ms / 1000.0) - elapsed_sec
                    if remaining_sec <= 0:
                        break

                    self._condition.wait(timeout=max(0.0001, remaining_sec))

                if not self._running and not self._queue:
                    break

                # Drain up to max_batch_size items
                count = min(len(self._queue), self.max_batch_size)
                for _ in range(count):
                    batch.append(self._queue.popleft())

            if not batch:
                continue

            self._process_batch(batch)

    def _process_batch(self, batch: List[BatchItem]) -> None:
        """Execute model batch inference and set results on all item events."""
        now = time.perf_counter()
        batch_size = len(batch)
        wait_times = [(now - item.enqueue_time) * 1000.0 for item in batch]
        avg_wait = sum(wait_times) / batch_size

        payloads = [item.payload for item in batch]
        exec_start = time.perf_counter()

        try:
            results = self.predict_fn(payloads)
            if len(results) != batch_size:
                raise ValueError(
                    f"Predict function returned {len(results)} items, "
                    f"expected {batch_size}"
                )

            for idx, item in enumerate(batch):
                item.result = results[idx]
                item.event.set()

        except Exception as exc:
            for item in batch:
                item.error = exc
                item.event.set()

        exec_duration_ms = (time.perf_counter() - exec_start) * 1000.0

        # Update telemetry
        with self._lock:
            self._total_requests += batch_size
            self._total_batches += 1
            self._total_batch_size_sum += batch_size
            self._total_wait_time_ms += avg_wait * batch_size
            self._total_exec_time_ms += exec_duration_ms

    def get_metrics(self) -> Dict[str, Any]:
        """Return operational batcher metrics and average execution latencies."""
        with self._lock:
            avg_batch = (
                round(self._total_batch_size_sum / self._total_batches, 2)
                if self._total_batches > 0
                else 0.0
            )
            avg_wait = (
                round(self._total_wait_time_ms / self._total_requests, 3)
                if self._total_requests > 0
                else 0.0
            )
            avg_exec = (
                round(self._total_exec_time_ms / self._total_batches, 3)
                if self._total_batches > 0
                else 0.0
            )

            return {
                "name": self.name,
                "max_batch_size": self.max_batch_size,
                "timeout_ms": self.timeout_ms,
                "total_requests": self._total_requests,
                "total_batches": self._total_batches,
                "average_batch_size": avg_batch,
                "average_wait_time_ms": avg_wait,
                "average_exec_time_ms": avg_exec,
                "queue_length": len(self._queue),
            }

    def __enter__(self) -> "DynamicBatcher":
        """Context manager entry point starting the worker thread."""
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit point stopping worker thread."""
        self.stop()
