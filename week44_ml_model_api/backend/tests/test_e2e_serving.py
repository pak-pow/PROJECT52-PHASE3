"""End-to-End Concurrency Stress and Chaos Testing Suite for PulseInfer Gateway."""

import base64
import concurrent.futures
import io
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pytest
from flask import Flask
from flask.testing import FlaskClient
from PIL import Image

from app.db.connection import get_db_connection
from data.seed import seed_database


def _generate_test_image_b64(
    size: Tuple[int, int] = (16, 16), color: Tuple[int, int, int] = (0, 128, 255)
) -> str:
    """Generate a base64 encoded PNG test image."""
    img = Image.new("RGB", size, color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


@pytest.fixture
def e2e_client(app: Flask, test_db_path: Path, temp_dir: Path) -> FlaskClient:
    """Fixture providing a seeded and fully preloaded client for E2E stress testing."""
    vault_dir = temp_dir / "models_vault"
    seed_database(db_path=test_db_path, vault_dir=vault_dir)

    registry = app.extensions.get("registry")
    if registry:
        conn = get_db_connection(test_db_path)
        registry.load_all_active_models(conn)
        conn.close()

    return app.test_client()


class TestConcurrentInferencePipeline:
    """Verify high-concurrency request handling, micro-batching, and cache speedup."""

    def test_high_concurrency_nlp_serving(self, e2e_client: FlaskClient) -> None:
        """Execute 50 parallel requests asserting batch coalescing and 100% success."""
        inputs = [
            f"Automated concurrency stress evaluation test sentence {idx}"
            for idx in range(50)
        ]

        def _send(txt: str) -> Tuple[int, Dict[str, Any]]:
            resp = e2e_client.post(
                "/api/v1/models/nlp-sentiment/predict",
                json={"text": txt},
            )
            return resp.status_code, resp.get_json()

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(_send, text) for text in inputs]
            results = [f.result() for f in futures]

        for status_code, data in results:
            assert status_code == 200
            assert data["status"] == "success"
            assert data["model_id"] == "nlp-sentiment"
            assert "sentiment" in data["prediction"]
            assert data["prediction"]["confidence"] > 0

        # Validate telemetry recorded requests
        metrics_resp = e2e_client.get("/api/v1/metrics?model_id=nlp-sentiment")
        assert metrics_resp.status_code == 200
        stats = metrics_resp.get_json()["metrics"]
        assert stats["total_requests"] >= 50
        assert stats["error_rate"] == 0.0

    def test_concurrent_cache_acceleration_under_load(
        self, e2e_client: FlaskClient
    ) -> None:
        """Verify identical concurrent queries achieve high cache hit ratio."""
        target_payload = {
            "text": "Highly repeatable canonical sentence for cache saturation testing."
        }

        # Prime the cache with an initial cold query
        cold_resp = e2e_client.post(
            "/api/v1/models/nlp-sentiment/predict", json=target_payload
        )
        assert cold_resp.status_code == 200

        def _send_identical() -> Tuple[int, Dict[str, Any]]:
            resp = e2e_client.post(
                "/api/v1/models/nlp-sentiment/predict",
                json=target_payload,
            )
            return resp.status_code, resp.get_json()

        # Fire 60 identical requests across 10 threads
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(_send_identical) for _ in range(60)]
            results = [f.result() for f in futures]

        cache_hits = 0
        for status_code, data in results:
            assert status_code == 200
            if data.get("cached"):
                cache_hits += 1

        # At least 50 of the 60 parallel requests should hit the cache
        assert cache_hits >= 50

        # Verify global telemetry metrics reflect high cache ratio
        metrics = e2e_client.get("/api/v1/metrics").get_json()["global"]
        assert metrics["cache_hits"] >= cache_hits


class TestChaosAndFaultIsolation:
    """Stress test gateway with concurrent corrupt, malformed, and missing payloads."""

    def test_concurrent_chaos_payload_isolation(self, e2e_client: FlaskClient) -> None:
        """Inject 60 concurrent valid and invalid payloads asserting isolation."""
        workload: List[Tuple[str, str, Dict[str, Any], int]] = []

        # 20 valid NLP requests
        for i in range(20):
            workload.append(
                (
                    "post",
                    "/api/v1/models/nlp-sentiment/predict",
                    {"text": f"Valid NLP input item {i}"},
                    200,
                )
            )

        # 10 malformed NLP requests (missing 'text')
        for i in range(10):
            workload.append(
                (
                    "post",
                    "/api/v1/models/nlp-sentiment/predict",
                    {"unexpected_key": f"bad {i}"},
                    400,
                )
            )

        # 10 non-existent model requests
        for i in range(10):
            workload.append(
                (
                    "post",
                    f"/api/v1/models/ghost-model-{i}/predict",
                    {"text": "Sample"},
                    404,
                )
            )

        # 10 valid Tabular fraud requests
        for i in range(10):
            workload.append(
                (
                    "post",
                    "/api/v1/models/fraud-detector/predict",
                    {
                        "transaction_amount": 100.0 + i,
                        "user_age": 25 + i,
                        "velocity_1h": 2,
                        "is_foreign": 0,
                    },
                    200,
                )
            )

        # 10 malformed Tabular requests (invalid structure: list instead of dict)
        for i in range(10):
            workload.append(
                (
                    "post",
                    "/api/v1/models/fraud-detector/predict",
                    ["invalid", "list", "payload", i],
                    400,
                )
            )

        def _execute_chaos_task(
            task: Tuple[str, str, Dict[str, Any], int],
        ) -> Tuple[int, int]:
            _, url, payload, expected_status = task
            resp = e2e_client.post(url, json=payload)
            return resp.status_code, expected_status

        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
            futures = [executor.submit(_execute_chaos_task, t) for t in workload]
            outcomes = [f.result() for f in futures]

        for actual_code, expected_code in outcomes:
            assert actual_code == expected_code

        # Confirm gateway remains healthy after the barrage
        health_resp = e2e_client.get("/api/health")
        assert health_resp.status_code == 200
        assert health_resp.get_json()["status"] == "healthy"


class TestZeroDowntimeHotSwapUnderLoad:
    """Validate model hot swapping while active client requests are in flight."""

    def test_hot_swap_during_active_traffic(self, e2e_client: FlaskClient) -> None:
        """Trigger version swap v1 -> v2-rc1 concurrently with 40 active predictions."""

        def _send_predict(idx: int) -> Tuple[int, str]:
            resp = e2e_client.post(
                "/api/v1/models/nlp-sentiment/predict",
                json={"text": f"In-flight request during hot-swap test {idx}"},
            )
            data = resp.get_json() or {}
            return resp.status_code, data.get("version", "")

        def _trigger_swap() -> Tuple[int, Dict[str, Any]]:
            resp = e2e_client.post(
                "/api/v1/models/nlp-sentiment/reload",
                json={"version": "v2-rc1"},
            )
            return resp.status_code, resp.get_json()

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            # Schedule 20 requests before swap
            futures_before = [executor.submit(_send_predict, i) for i in range(20)]
            # Schedule the hot-swap
            future_swap = executor.submit(_trigger_swap)
            # Schedule 20 requests during/after swap
            futures_after = [executor.submit(_send_predict, i + 20) for i in range(20)]

            swap_status, swap_data = future_swap.result()
            results_before = [f.result() for f in futures_before]
            results_after = [f.result() for f in futures_after]

        # Swap must succeed with 200
        assert swap_status == 200
        assert swap_data["status"] == "success"
        assert swap_data["active_version"] == "v2-rc1"

        # Every prediction request must have succeeded without dropped connections
        for code, _ in results_before + results_after:
            assert code == 200

        # Post-swap inspection confirms active version is now v2-rc1
        detail_resp = e2e_client.get("/api/v1/models/nlp-sentiment")
        assert detail_resp.status_code == 200
        assert detail_resp.get_json()["model"]["active_version"] == "v2-rc1"

        # Subsequent prediction uses v2-rc1
        post_resp = e2e_client.post(
            "/api/v1/models/nlp-sentiment/predict",
            json={"text": "Confirmed post-swap inference sentence."},
        )
        assert post_resp.status_code == 200
        assert post_resp.get_json()["version"] == "v2-rc1"


class TestMultiDomainConcurrentServing:
    """Stress test concurrent traffic spanning NLP, Vision, and Tabular models."""

    def test_cross_domain_parallel_inference(self, e2e_client: FlaskClient) -> None:
        """Issue 45 parallel requests distributed across all three domain models."""
        img_b64 = _generate_test_image_b64()

        tasks = []
        for i in range(15):
            tasks.append(
                (
                    "/api/v1/models/nlp-sentiment/predict",
                    {"text": f"Cross domain NLP sentence {i}"},
                    "sentiment",
                )
            )
            tasks.append(
                (
                    "/api/v1/models/vision-classifier/predict",
                    {"image_base64": img_b64},
                    "top_class",
                )
            )
            tasks.append(
                (
                    "/api/v1/models/fraud-detector/predict",
                    {
                        "transaction_amount": 50.0 * (i + 1),
                        "user_age": 20 + i,
                        "velocity_1h": 1,
                        "is_foreign": 0,
                    },
                    "risk_score",
                )
            )

        def _execute(url: str, payload: dict, expected_key: str) -> bool:
            resp = e2e_client.post(url, json=payload)
            if resp.status_code != 200:
                return False
            data = resp.get_json()
            return expected_key in data.get("prediction", {})

        with concurrent.futures.ThreadPoolExecutor(max_workers=9) as executor:
            futures = [
                executor.submit(_execute, url, payload, key)
                for url, payload, key in tasks
            ]
            results = [f.result() for f in futures]

        assert all(results)
        assert len(results) == 45

        # Check telemetry covers all three models
        metrics_resp = e2e_client.get("/api/v1/metrics")
        assert metrics_resp.status_code == 200
        models_data = metrics_resp.get_json()["models"]
        assert "nlp-sentiment" in models_data
        assert "vision-classifier" in models_data
        assert "fraud-detector" in models_data


class TestOperationalTelemetryUnderLoad:
    """Validate runtime administration endpoints under parallel traffic."""

    def test_telemetry_reset_and_cache_purge_during_load(
        self, e2e_client: FlaskClient
    ) -> None:
        """Trigger cache purge and telemetry reset concurrently with inference."""

        def _send_load(idx: int) -> int:
            resp = e2e_client.post(
                "/api/v1/models/nlp-sentiment/predict",
                json={"text": f"Reset load payload {idx}"},
            )
            return resp.status_code

        def _admin_action(url: str) -> int:
            resp = e2e_client.post(url)
            return resp.status_code

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            load_futures = [executor.submit(_send_load, i) for i in range(25)]
            clear_cache_future = executor.submit(_admin_action, "/api/v1/cache/clear")
            reset_metrics_future = executor.submit(
                _admin_action, "/api/v1/metrics/reset"
            )

            load_codes = [f.result() for f in load_futures]
            cache_code = clear_cache_future.result()
            reset_code = reset_metrics_future.result()

        assert all(code == 200 for code in load_codes)
        assert cache_code == 200
        assert reset_code == 200

        # Health endpoint remains operational
        health = e2e_client.get("/api/health").get_json()
        assert health["status"] == "healthy"
