"""Comprehensive unit tests for ModelRegistry and TelemetryEngine services."""

import json
import time
from pathlib import Path

import pytest

from app.db.connection import get_db_connection
from app.models.model_entity import ModelDAO
from app.models.model_version import ModelVersionDAO
from app.models.prediction_log import PredictionLogDAO
from app.services.cache_service import InferenceCache
from app.services.registry_service import (
    ModelLifecycleState,
    ModelRegistry,
)
from app.services.telemetry_service import TelemetryEngine
from data.seed import seed_database


class TestTelemetryEngine:
    """Unit tests for the TelemetryEngine latency histogram service."""

    def test_record_single_and_metrics(self) -> None:
        telemetry = TelemetryEngine(window_size=100)
        telemetry.record(
            model_id="nlp-model",
            version="v1",
            latency_ms=12.5,
            cached=False,
            status="success",
        )

        global_metrics = telemetry.get_global_metrics()
        assert global_metrics["total_requests"] == 1
        assert global_metrics["successful_requests"] == 1
        assert global_metrics["failed_requests"] == 0
        assert global_metrics["cache_hits"] == 0
        assert global_metrics["cache_hit_ratio"] == 0.0
        assert global_metrics["error_rate"] == 0.0
        assert global_metrics["latencies"]["p50"] == 12.5
        assert global_metrics["latencies"]["avg"] == 12.5

    def test_percentiles_calculation(self) -> None:
        telemetry = TelemetryEngine(window_size=100)
        latencies = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]

        for lat in latencies:
            telemetry.record("test-model", "v1", lat, cached=False)

        metrics = telemetry.get_model_metrics("test-model")
        assert metrics["total_requests"] == 10
        assert metrics["latencies"]["min"] == 10.0
        assert metrics["latencies"]["max"] == 100.0
        assert metrics["latencies"]["avg"] == 55.0
        assert metrics["latencies"]["p50"] == pytest.approx(55.0, abs=1.0)
        assert metrics["latencies"]["p90"] == pytest.approx(91.0, abs=2.0)
        assert metrics["latencies"]["p99"] == pytest.approx(99.1, abs=1.0)

    def test_empty_metrics_and_reset(self) -> None:
        telemetry = TelemetryEngine(window_size=50)
        empty_metrics = telemetry.get_global_metrics()
        assert empty_metrics["total_requests"] == 0
        assert empty_metrics["latencies"]["p50"] == 0.0
        assert empty_metrics["latencies"]["avg"] == 0.0

        telemetry.record("m1", "v1", 25.0)
        assert telemetry.get_global_metrics()["total_requests"] == 1
        telemetry.reset()
        assert telemetry.get_global_metrics()["total_requests"] == 0

    def test_cache_hits_and_error_rate(self) -> None:
        telemetry = TelemetryEngine(window_size=100)
        telemetry.record("m1", "v1", 0.05, cached=True, status="success")
        telemetry.record("m1", "v1", 10.0, cached=False, status="success")
        telemetry.record("m1", "v1", 5.0, cached=False, status="error")

        m1_metrics = telemetry.get_model_metrics("m1")
        assert m1_metrics["total_requests"] == 3
        assert m1_metrics["cache_hits"] == 1
        assert m1_metrics["failed_requests"] == 1
        assert m1_metrics["cache_hit_ratio"] == pytest.approx(0.3333, abs=0.01)
        assert m1_metrics["error_rate"] == pytest.approx(0.3333, abs=0.01)

        all_models = telemetry.get_all_models_metrics()
        assert "m1" in all_models

    def test_sliding_window_eviction_and_throughput(self) -> None:
        telemetry = TelemetryEngine(window_size=5)
        for i in range(10):
            telemetry.record("m1", "v1", float(i))
            time.sleep(0.001)

        metrics = telemetry.get_global_metrics()
        # Window size is capped at 5
        assert metrics["window_samples"] == 5
        assert metrics["throughput_rps"] > 0.0


class TestModelRegistry:
    """Unit tests for the ModelRegistry lifecycle service."""

    @pytest.fixture
    def setup_registry(self, tmp_path: Path):
        """Fixture seeding database and initializing registry."""
        db_path = tmp_path / "registry_test.db"
        vault_dir = tmp_path / "models_vault"
        seed_database(db_path=db_path, vault_dir=vault_dir)

        conn = get_db_connection(db_path)
        cache = InferenceCache(max_size=50)
        telemetry = TelemetryEngine(window_size=50)

        registry = ModelRegistry(
            cache=cache,
            telemetry=telemetry,
            max_batch_size=4,
            batch_timeout_ms=15.0,
        )

        yield registry, conn, vault_dir, db_path

        registry.shutdown()
        conn.close()

    def test_load_model_lifecycle(self, setup_registry) -> None:
        registry, conn, _, _ = setup_registry

        # Load NLP model
        reg_nlp = registry.load_model("nlp-sentiment", conn)
        assert reg_nlp.model_id == "nlp-sentiment"
        assert reg_nlp.state == ModelLifecycleState.ACTIVE
        assert reg_nlp.active_version == "v1"

        # Load Vision model
        reg_vis = registry.load_model("vision-classifier", conn)
        assert reg_vis.model_id == "vision-classifier"

        # Load Tabular model
        reg_tab = registry.load_model("fraud-detector", conn)
        assert reg_tab.model_id == "fraud-detector"

        assert len(registry.list_models()) == 3

    def test_load_all_active_models(self, setup_registry) -> None:
        registry, conn, _, _ = setup_registry
        count = registry.load_all_active_models(conn)
        assert count == 3
        assert len(registry.list_models()) == 3

    def test_load_model_errors(self, setup_registry) -> None:
        registry, conn, _, _ = setup_registry

        with pytest.raises(ValueError) as exc:
            registry.load_model("non-existent-model", conn)
        assert "does not exist in registry database" in str(exc.value)

        with pytest.raises(ValueError) as exc:
            registry.load_model("nlp-sentiment", conn, version="v999")
        assert "Version 'v999' for model 'nlp-sentiment' not found" in str(exc.value)

    def test_validate_input(self, setup_registry) -> None:
        registry, conn, _, _ = setup_registry
        registry.load_model("nlp-sentiment", conn)
        registry.load_model("vision-classifier", conn)
        registry.load_model("fraud-detector", conn)

        # None payload
        ok, err = registry.validate_input("nlp-sentiment", None)
        assert ok is False
        assert "cannot be None" in str(err)

        # NLP validation
        ok_nlp, _ = registry.validate_input("nlp-sentiment", {"text": "hello world"})
        assert ok_nlp is True
        ok_nlp_str, _ = registry.validate_input("nlp-sentiment", "hello world")
        assert ok_nlp_str is True
        bad_nlp, _ = registry.validate_input("nlp-sentiment", {"foo": "bar"})
        assert bad_nlp is False

        # Vision validation
        ok_vis, _ = registry.validate_input(
            "vision-classifier", {"image_base64": "abc"}
        )
        assert ok_vis is True
        bad_vis, _ = registry.validate_input("vision-classifier", {"wrong_key": 123})
        assert bad_vis is False

        # Tabular validation
        ok_tab, _ = registry.validate_input(
            "fraud-detector", {"transaction_amount": 100.0}
        )
        assert ok_tab is True
        bad_tab, _ = registry.validate_input("fraud-detector", "not a dict")
        assert bad_tab is False

        # Unregistered model
        ok_unreg, _ = registry.validate_input("unregistered", {})
        assert ok_unreg is False

    def test_predict_end_to_end_and_cache(self, setup_registry) -> None:
        registry, conn, _, _ = setup_registry
        registry.load_model("nlp-sentiment", conn)

        payload = {"text": "This is great, fantastic speed!"}

        # Query 1: Cache Miss
        res1 = registry.predict("nlp-sentiment", payload, use_cache=True, conn=conn)
        assert res1["status"] == "success"
        assert res1["cached"] is False
        assert res1["prediction"]["sentiment"] == "positive"
        assert res1["latency_ms"] >= 0.0

        # Query 2: Cache Hit
        res2 = registry.predict("nlp-sentiment", payload, use_cache=True, conn=conn)
        assert res2["cached"] is True
        assert res2["prediction"]["sentiment"] == "positive"
        assert res2["latency_ms"] <= 1.0

        # Verify DB logs were created
        logs = PredictionLogDAO.get_recent(conn, model_id="nlp-sentiment")
        assert len(logs) == 2

    def test_predict_direct_without_batcher(self, setup_registry) -> None:
        registry, conn, _, _ = setup_registry
        registry.load_model("fraud-detector", conn)

        payload = {
            "transaction_amount": 25.0,
            "user_age": 40,
            "velocity_1h": 0,
            "is_foreign": 0,
        }
        res = registry.predict(
            "fraud-detector",
            payload,
            use_cache=False,
            use_batcher=False,
            conn=conn,
        )
        assert res["status"] == "success"
        assert res["prediction"]["risk_level"] == "LOW"

    def test_predict_validation_failure(self, setup_registry) -> None:
        registry, conn, _, _ = setup_registry
        registry.load_model("nlp-sentiment", conn)

        with pytest.raises(ValueError) as exc:
            registry.predict(
                "nlp-sentiment", {"wrong_field": 123}, use_cache=False, conn=conn
            )
        assert "must contain 'text'" in str(exc.value)

        # Error should be recorded in telemetry
        telemetry = registry.telemetry.get_model_metrics("nlp-sentiment")
        assert telemetry["failed_requests"] == 1

    def test_predict_batch(self, setup_registry) -> None:
        registry, conn, _, _ = setup_registry
        registry.load_model("nlp-sentiment", conn)

        batch_payload = [
            {"text": "Great excellent performance!"},
            {"text": "Awful experience, terrible!"},
        ]
        results = registry.predict_batch("nlp-sentiment", batch_payload, conn=conn)
        assert len(results) == 2
        assert results[0]["sentiment"] == "positive"
        assert results[1]["sentiment"] == "negative"

        # Check telemetry recorded batch size
        telemetry = registry.telemetry.get_model_metrics("nlp-sentiment")
        assert telemetry["total_requests"] == 2

    def test_hot_swap_zero_downtime(self, setup_registry) -> None:
        registry, conn, vault_dir, _ = setup_registry
        registry.load_model("nlp-sentiment", conn)

        # Create v2 weights artifact on disk
        v2_path = vault_dir / "nlp-sentiment" / "v2" / "weights.json"
        v2_path.parent.mkdir(parents=True, exist_ok=True)
        v2_weights = {
            "model_id": "nlp-sentiment",
            "version": "v2",
            "classes": ["negative", "neutral", "positive"],
            "vocabulary": {
                "phenomenal": 3.0,
                "superb": 2.5,
                "dreadful": -3.0,
            },
            "bias": [0.1, 0.5, 0.1],
        }
        v2_path.write_text(json.dumps(v2_weights, indent=2), encoding="utf-8")

        # Register v2 in database
        ModelVersionDAO.create(
            conn=conn,
            model_id="nlp-sentiment",
            version="v2",
            artifact_path=str(v2_path),
            input_schema={"text": "string"},
            output_schema={"sentiment": "string"},
            metrics={"accuracy": 0.985},
            status="staging",
        )

        # Execute query on v1
        res_v1 = registry.predict(
            "nlp-sentiment", {"text": "phenomenal"}, use_cache=True, conn=conn
        )
        assert res_v1["version"] == "v1"

        # Perform Zero-Downtime Hot Swap to v2
        registry.hot_swap_version("nlp-sentiment", "v2", conn)

        # Verify active version in registry and database
        status = registry.get_model_status("nlp-sentiment")
        assert status["active_version"] == "v2"
        db_model = ModelDAO.get_by_id(conn, "nlp-sentiment")
        assert db_model["active_version"] == "v2"

        # Query on v2
        res_v2 = registry.predict(
            "nlp-sentiment", {"text": "phenomenal"}, use_cache=True, conn=conn
        )
        assert res_v2["version"] == "v2"
        assert res_v2["prediction"]["sentiment"] == "positive"
        assert res_v2["cached"] is False  # Cache was invalidated for this model

    def test_hot_swap_error_handling(self, setup_registry) -> None:
        registry, conn, _, _ = setup_registry
        registry.load_model("nlp-sentiment", conn)

        # Target version not in DB
        with pytest.raises(ValueError) as exc:
            registry.hot_swap_version("nlp-sentiment", "v999", conn)
        assert "not found" in str(exc.value)

        # Target version file missing -> RuntimeError
        ModelVersionDAO.create(
            conn=conn,
            model_id="nlp-sentiment",
            version="v_missing",
            artifact_path="/invalid/path/nonexistent.json",
            status="active",
        )
        with pytest.raises(RuntimeError) as exc:
            registry.hot_swap_version("nlp-sentiment", "v_missing", conn)
        assert "Hot swap failed" in str(exc.value)

        # Verify model remains ACTIVE on v1
        assert registry.get_model_status("nlp-sentiment")["active_version"] == "v1"

    def test_unload_model_and_shutdown(self, setup_registry) -> None:
        registry, conn, _, _ = setup_registry
        registry.load_model("nlp-sentiment", conn)

        assert registry.unload_model("nlp-sentiment") is True
        assert registry.unload_model("nlp-sentiment") is False  # already unloaded

        with pytest.raises(KeyError):
            registry.predict("nlp-sentiment", {"text": "hi"})

        # Load multiple and shutdown
        registry.load_model("vision-classifier", conn)
        registry.load_model("fraud-detector", conn)
        assert len(registry.list_models()) == 2

        registry.shutdown()
        assert len(registry.list_models()) == 0
