"""Comprehensive unit tests for InferenceCache and DynamicBatcher services."""

import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, List

import numpy as np
import pytest

from app.services.batcher_service import BatchItem, DynamicBatcher
from app.services.cache_service import InferenceCache


class TestInferenceCache:
    """Unit tests for the InferenceCache service."""

    def test_cache_set_and_get(self) -> None:
        cache = InferenceCache(max_size=10, ttl_seconds=60)
        cache.set("key1", {"result": "positive"})

        val = cache.get("key1")
        assert val == {"result": "positive"}

        miss = cache.get("non_existent_key")
        assert miss is None

        stats = cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_ratio"] == 0.5

    def test_cache_lru_eviction(self) -> None:
        cache = InferenceCache(max_size=3, ttl_seconds=60)
        cache.set("k1", 1)
        cache.set("k2", 2)
        cache.set("k3", 3)

        # Access k1 to make it recently used
        assert cache.get("k1") == 1

        # Inserting k4 should evict k2 (least recently used)
        cache.set("k4", 4)
        assert cache.get("k2") is None
        assert cache.get("k1") == 1
        assert cache.get("k3") == 3
        assert cache.get("k4") == 4

        stats = cache.get_stats()
        assert stats["evictions"] == 1
        assert stats["size"] == 3

    def test_cache_ttl_expiration(self) -> None:
        cache = InferenceCache(max_size=10, ttl_seconds=1)
        cache.set("short_key", "value", ttl_seconds=1)

        # Immediate read
        assert cache.get("short_key") == "value"

        # Wait for expiration
        time.sleep(1.1)
        assert cache.get("short_key") is None

    def test_cache_purge_expired(self) -> None:
        cache = InferenceCache(max_size=10, ttl_seconds=1)
        cache.set("exp1", 100, ttl_seconds=1)
        cache.set("exp2", 200, ttl_seconds=1)
        cache.set("perm", 300, ttl_seconds=60)

        time.sleep(1.1)
        purged = cache.purge_expired()
        assert purged == 2
        assert cache.get("perm") == 300

    def test_cache_invalidation_and_clear(self) -> None:
        cache = InferenceCache(max_size=10)
        cache.set("nlp:v1:abc", 1)
        cache.set("nlp:v1:xyz", 2)
        cache.set("vision:v1:123", 3)

        assert cache.invalidate("nlp:v1:abc") is True
        assert cache.invalidate("nlp:v1:abc") is False

        # Invalidate by model prefix
        removed = cache.invalidate_model("nlp", "v1")
        assert removed == 1
        assert cache.get("nlp:v1:xyz") is None
        assert cache.get("vision:v1:123") == 3

        cache.clear()
        assert cache.get_stats()["size"] == 0

    def test_canonical_hash_consistency(self) -> None:
        # Different dictionary key ordering must yield identical hash
        p1 = {"text": "hello", "domain": "nlp", "metadata": {"flag": True}}
        p2 = {"domain": "nlp", "metadata": {"flag": True}, "text": "hello"}

        h1 = InferenceCache.compute_hash("m1", "v1", p1)
        h2 = InferenceCache.compute_hash("m1", "v1", p2)
        assert h1 == h2

        # Different version or model id yields different hash
        h3 = InferenceCache.compute_hash("m1", "v2", p1)
        assert h1 != h3

        # List, scalar, and numpy array support
        arr = np.array([1.0, 2.0, 3.0], dtype=np.float32)
        h_arr = InferenceCache.compute_hash("m2", "v1", arr)
        assert isinstance(h_arr, str) and len(h_arr) == 64

        # List/tuple and float canonicalization
        p_list = {"values": [1.123456789, 2.5]}
        h_list = InferenceCache.compute_hash("m1", "v1", p_list)
        assert isinstance(h_list, str) and len(h_list) == 64

        # Object that cannot be JSON serialized
        class NonSerializable:
            pass

        h_obj = InferenceCache.compute_hash("m3", "v1", NonSerializable())
        assert isinstance(h_obj, str) and len(h_obj) == 64

    def test_cache_thread_safety(self) -> None:
        cache = InferenceCache(max_size=50)

        def worker(worker_id: int) -> None:
            for i in range(25):
                key = f"key_{i}"
                cache.set(key, f"val_{worker_id}_{i}")
                _ = cache.get(key)

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(worker, idx) for idx in range(4)]
            for f in futures:
                f.result()

        stats = cache.get_stats()
        assert stats["size"] <= 50
        cache.reset_stats()
        assert cache.get_stats()["hits"] == 0


class TestDynamicBatcher:
    """Unit tests for the DynamicBatcher service."""

    def test_single_item_prediction(self) -> None:
        def mock_predict(batch: List[str]) -> List[str]:
            return [f"processed:{item}" for item in batch]

        batcher = DynamicBatcher(
            predict_fn=mock_predict,
            max_batch_size=4,
            timeout_ms=50.0,
        )
        # Idempotent start and stop
        batcher.start()
        batcher.start()  # second call should be no-op
        res = batcher.submit("input_data", timeout=2.0)
        assert res == "processed:input_data"
        batcher.stop()
        batcher.stop()  # second call should be no-op

    def test_batch_capacity_trigger(self) -> None:
        # Check that reaching max_batch_size executes immediately
        def mock_predict(batch: List[int]) -> List[int]:
            return [x * 2 for x in batch]

        batcher = DynamicBatcher(
            predict_fn=mock_predict,
            max_batch_size=3,
            timeout_ms=500.0,  # High timeout; batch size trigger should fire first
        )

        with batcher:
            with ThreadPoolExecutor(max_workers=3) as executor:
                start_time = time.perf_counter()
                futures = [executor.submit(batcher.submit, i, 2.0) for i in [1, 2, 3]]
                results = [f.result() for f in futures]
                elapsed = time.perf_counter() - start_time

            assert results == [2, 4, 6]
            # Should have completed significantly faster than 500ms timeout
            assert elapsed < 0.35

            metrics = batcher.get_metrics()
            assert metrics["total_requests"] == 3
            assert metrics["total_batches"] == 1
            assert metrics["average_batch_size"] == 3.0

    def test_batch_timeout_trigger(self) -> None:
        # Check that a partial batch triggers once timeout_ms expires
        def mock_predict(batch: List[str]) -> List[str]:
            return [s.upper() for s in batch]

        batcher = DynamicBatcher(
            predict_fn=mock_predict,
            max_batch_size=10,  # We only submit 1 item
            timeout_ms=25.0,
        )

        with batcher:
            start_time = time.perf_counter()
            result = batcher.submit("hello", timeout=1.0)
            elapsed = (time.perf_counter() - start_time) * 1000.0

            assert result == "HELLO"
            assert elapsed >= 20.0  # Waited for timeout window

    def test_concurrent_batch_processing(self) -> None:
        def mock_predict(batch: List[int]) -> List[int]:
            time.sleep(0.01)  # Synthetic compute duration
            return [x**2 for x in batch]

        batcher = DynamicBatcher(
            predict_fn=mock_predict,
            max_batch_size=4,
            timeout_ms=30.0,
        )

        num_requests = 16
        with batcher:
            with ThreadPoolExecutor(max_workers=8) as executor:
                futures = [
                    executor.submit(batcher.submit, i, 5.0) for i in range(num_requests)
                ]
                results = [f.result() for f in futures]

            assert results == [i**2 for i in range(num_requests)]
            metrics = batcher.get_metrics()
            assert metrics["total_requests"] == 16
            # Total batches should be significantly fewer than 16 (aggregated)
            assert metrics["total_batches"] < 16
            assert metrics["average_batch_size"] > 1.0

    def test_error_propagation_to_batch_items(self) -> None:
        def failing_predict(batch: List[Any]) -> List[Any]:
            raise ValueError("Inference kernel crashed")

        batcher = DynamicBatcher(
            predict_fn=failing_predict,
            max_batch_size=2,
            timeout_ms=20.0,
        )

        with batcher:
            with pytest.raises(ValueError) as exc_info:
                batcher.submit("test_item", timeout=1.0)
            assert "Inference kernel crashed" in str(exc_info.value)

    def test_result_length_mismatch(self) -> None:
        def faulty_predict(batch: List[Any]) -> List[Any]:
            return []  # Returns 0 results instead of len(batch)

        batcher = DynamicBatcher(
            predict_fn=faulty_predict,
            max_batch_size=1,
            timeout_ms=10.0,
        )

        with batcher:
            with pytest.raises(ValueError) as exc_info:
                batcher.submit("item", timeout=1.0)
            assert "expected 1" in str(exc_info.value)

    def test_submit_not_running_raises_error(self) -> None:
        batcher = DynamicBatcher(
            predict_fn=lambda b: b,
            max_batch_size=2,
        )
        # Not started
        with pytest.raises(RuntimeError):
            batcher.submit("item")

    def test_submit_timeout_raises_error(self) -> None:
        def stalling_predict(batch: List[Any]) -> List[Any]:
            time.sleep(0.5)
            return batch

        batcher = DynamicBatcher(
            predict_fn=stalling_predict,
            max_batch_size=1,
            timeout_ms=10.0,
        )

        with batcher:
            with pytest.raises(TimeoutError):
                batcher.submit("item", timeout=0.05)

    def test_stop_aborts_queued_items(self) -> None:
        batcher = DynamicBatcher(
            predict_fn=lambda b: b,
            max_batch_size=10,
        )
        batcher._running = True  # set running state without starting worker thread
        item = BatchItem(payload="lingering", enqueue_time=time.perf_counter())
        batcher._queue.append(item)
        batcher.stop()

        assert item.event.is_set()
        assert isinstance(item.error, RuntimeError)
        assert "stopped before execution" in str(item.error)


class TestIntegratedBatcherAndCache:
    """Verifies seamless integration between InferenceCache and DynamicBatcher."""

    def test_cache_bypasses_batcher_for_repeated_queries(self) -> None:
        execution_count = 0

        def mock_predict(batch: List[str]) -> List[str]:
            nonlocal execution_count
            execution_count += len(batch)
            return [f"result_for_{item}" for item in batch]

        cache = InferenceCache(max_size=100)
        batcher = DynamicBatcher(
            predict_fn=mock_predict,
            max_batch_size=4,
            timeout_ms=20.0,
        )

        def query(payload: str) -> str:
            cache_key = cache.compute_hash("test-model", "v1", payload)
            cached_result = cache.get(cache_key)
            if cached_result is not None:
                return cached_result

            computed = batcher.submit(payload, timeout=2.0)
            cache.set(cache_key, computed)
            return computed

        with batcher:
            # Query 1: Misses cache, executes via batcher
            r1 = query("query_apple")
            assert r1 == "result_for_query_apple"
            assert execution_count == 1

            # Query 2: Repeated payload, hits cache instantly
            r2 = query("query_apple")
            assert r2 == "result_for_query_apple"
            assert execution_count == 1  # No additional batcher execution

            # Query 3: New payload, executes via batcher
            r3 = query("query_banana")
            assert r3 == "result_for_query_banana"
            assert execution_count == 2

            stats = cache.get_stats()
            assert stats["hits"] == 1
            assert stats["misses"] == 2
