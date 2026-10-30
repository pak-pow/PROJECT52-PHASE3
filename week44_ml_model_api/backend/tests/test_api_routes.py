"""Comprehensive integration tests for REST API gateway and inference routes."""

import base64
import io
import json
from pathlib import Path

import pytest
from flask.testing import FlaskClient
from PIL import Image

from app.models.model_version import ModelVersionDAO
from data.seed import seed_database


def _make_test_image_b64(size: tuple = (16, 16), color: tuple = (255, 0, 0)) -> str:
    """Helper creating base64 encoded PNG for vision testing."""
    img = Image.new("RGB", size, color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


@pytest.fixture
def seeded_client(app, test_db_path: Path, temp_dir: Path) -> FlaskClient:
    """Seed test database and vault with default models and return client."""
    vault_dir = temp_dir / "models_vault"
    seed_database(db_path=test_db_path, vault_dir=vault_dir)

    # Preload models into registry
    registry = app.extensions.get("registry")
    if registry:
        from app.db.connection import get_db_connection

        conn = get_db_connection(test_db_path)
        registry.load_all_active_models(conn)
        conn.close()

    return app.test_client()


class TestModelCatalogRoutes:
    """Tests for model catalog discovery and metadata inspection endpoints."""

    def test_list_models_empty(self, client: FlaskClient) -> None:
        resp = client.get("/api/v1/models")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        assert data["count"] == 0
        assert data["models"] == []

    def test_list_models_seeded(self, seeded_client: FlaskClient) -> None:
        resp = seeded_client.get("/api/v1/models")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        assert data["count"] == 3
        model_ids = [m["model_id"] for m in data["models"]]
        assert "nlp-sentiment" in model_ids
        assert "vision-classifier" in model_ids
        assert "fraud-detector" in model_ids

    def test_list_models_domain_filter(self, seeded_client: FlaskClient) -> None:
        # NLP filter
        resp_nlp = seeded_client.get("/api/v1/models?domain=nlp")
        assert resp_nlp.status_code == 200
        data_nlp = resp_nlp.get_json()
        assert data_nlp["count"] == 1
        assert data_nlp["models"][0]["model_id"] == "nlp-sentiment"

        # Vision filter
        resp_vis = seeded_client.get("/api/v1/models?domain=vision")
        assert resp_vis.status_code == 200
        assert resp_vis.get_json()["count"] == 1

        # Non-existent domain filter
        resp_none = seeded_client.get("/api/v1/models?domain=audio")
        assert resp_none.status_code == 200
        assert resp_none.get_json()["count"] == 0

    def test_get_model_detail(self, seeded_client: FlaskClient) -> None:
        resp = seeded_client.get("/api/v1/models/nlp-sentiment")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        model = data["model"]
        assert model["model_id"] == "nlp-sentiment"
        assert model["domain"] == "nlp"
        assert model["active_version"] == "v1"
        assert "batcher" in model
        assert "telemetry" in model

    def test_get_model_detail_not_found(self, seeded_client: FlaskClient) -> None:
        resp = seeded_client.get("/api/v1/models/non-existent-id")
        assert resp.status_code == 404
        data = resp.get_json()
        assert data["status"] == "error"
        assert "not found" in data["error"]

    def test_get_model_metadata(self, seeded_client: FlaskClient) -> None:
        resp = seeded_client.get("/api/v1/models/nlp-sentiment/metadata")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        assert data["model_id"] == "nlp-sentiment"
        assert "input_schema" in data
        assert "output_schema" in data
        assert len(data["versions"]) >= 1
        assert data["versions"][0]["version"] == "v1"

    def test_get_model_metadata_not_found(self, seeded_client: FlaskClient) -> None:
        resp = seeded_client.get("/api/v1/models/unknown-model/metadata")
        assert resp.status_code == 404


class TestInferenceRoutes:
    """Tests for single-item and batch inference endpoints."""

    def test_predict_nlp_single(self, seeded_client: FlaskClient) -> None:
        payload = {"text": "Great service and excellent performance!"}
        resp = seeded_client.post("/api/v1/models/nlp-sentiment/predict", json=payload)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        assert data["model_id"] == "nlp-sentiment"
        assert data["version"] == "v1"
        assert data["prediction"]["sentiment"] == "positive"
        assert data["cached"] is False

        # Query 2: Repeated request should hit prediction cache
        resp2 = seeded_client.post("/api/v1/models/nlp-sentiment/predict", json=payload)
        assert resp2.status_code == 200
        data2 = resp2.get_json()
        assert data2["cached"] is True
        assert data2["prediction"]["sentiment"] == "positive"

    def test_predict_nlp_bypass_cache_and_batcher(
        self, seeded_client: FlaskClient
    ) -> None:
        payload = {"text": "Neutral statement here."}
        url = "/api/v1/models/nlp-sentiment/predict?use_cache=false&use_batcher=false"
        resp = seeded_client.post(url, json=payload)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        assert data["cached"] is False

    def test_predict_vision_single(self, seeded_client: FlaskClient) -> None:
        b64_img = _make_test_image_b64(size=(16, 16))
        payload = {"image_base64": b64_img}
        resp = seeded_client.post(
            "/api/v1/models/vision-classifier/predict", json=payload
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        assert "top_class" in data["prediction"]
        assert "class_scores" in data["prediction"]

    def test_predict_tabular_single(self, seeded_client: FlaskClient) -> None:
        payload = {
            "transaction_amount": 2500.0,
            "user_age": 21,
            "velocity_1h": 7,
            "is_foreign": 1,
        }
        resp = seeded_client.post("/api/v1/models/fraud-detector/predict", json=payload)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        assert "risk_score" in data["prediction"]
        assert data["prediction"]["is_flagged"] is True
        assert data["prediction"]["risk_level"] == "HIGH"

    def test_predict_validation_errors(self, seeded_client: FlaskClient) -> None:
        # None / empty body
        resp_empty = seeded_client.post(
            "/api/v1/models/nlp-sentiment/predict",
            data="not a json",
            content_type="text/plain",
        )
        assert resp_empty.status_code == 400
        assert "Request body must be a valid JSON" in resp_empty.get_json()["error"]

        # Missing required 'text' key for NLP
        resp_nlp_bad = seeded_client.post(
            "/api/v1/models/nlp-sentiment/predict", json={"unknown_key": "abc"}
        )
        assert resp_nlp_bad.status_code == 400
        assert "must contain 'text'" in resp_nlp_bad.get_json()["error"]

        # Non-dict tabular payload
        resp_tab_bad = seeded_client.post(
            "/api/v1/models/fraud-detector/predict", json="not a dictionary"
        )
        assert resp_tab_bad.status_code == 400

    def test_predict_model_not_found(self, seeded_client: FlaskClient) -> None:
        resp = seeded_client.post(
            "/api/v1/models/ghost-model/predict", json={"text": "hello"}
        )
        assert resp.status_code == 404

    def test_predict_timeout_error(self, seeded_client: FlaskClient) -> None:
        from unittest.mock import patch

        with patch("app.services.registry_service.ModelRegistry.predict") as mock_p:
            mock_p.side_effect = TimeoutError("Request timed out waiting for batch")
            resp = seeded_client.post(
                "/api/v1/models/nlp-sentiment/predict", json={"text": "hello"}
            )
            assert resp.status_code == 504
            assert "timed out" in resp.get_json()["error"]

    def test_predict_internal_error(self, seeded_client: FlaskClient) -> None:
        from unittest.mock import patch

        with patch("app.services.registry_service.ModelRegistry.predict") as mock_p:
            mock_p.side_effect = RuntimeError("Fatal GPU/CPU arithmetic fault")
            resp = seeded_client.post(
                "/api/v1/models/nlp-sentiment/predict", json={"text": "hello"}
            )
            assert resp.status_code == 500
            assert "Inference execution failed" in resp.get_json()["error"]

    def test_predict_batch_dict_format(self, seeded_client: FlaskClient) -> None:
        payload = {
            "inputs": [
                {"text": "Great service!"},
                {"text": "Awful and terrible!"},
            ]
        }
        resp = seeded_client.post(
            "/api/v1/models/nlp-sentiment/predict-batch", json=payload
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        assert data["batch_size"] == 2
        assert len(data["predictions"]) == 2
        assert data["predictions"][0]["sentiment"] == "positive"
        assert data["predictions"][1]["sentiment"] == "negative"

    def test_predict_batch_list_format(self, seeded_client: FlaskClient) -> None:
        payload = [
            {"text": "Great experience!"},
            {"text": "Slow and bad!"},
        ]
        resp = seeded_client.post(
            "/api/v1/models/nlp-sentiment/predict-batch", json=payload
        )
        assert resp.status_code == 200
        assert resp.get_json()["batch_size"] == 2

    def test_predict_batch_errors(self, seeded_client: FlaskClient) -> None:
        # Empty inputs list
        resp = seeded_client.post(
            "/api/v1/models/nlp-sentiment/predict-batch", json={"inputs": []}
        )
        assert resp.status_code == 400

        # Invalid body
        resp_inv = seeded_client.post(
            "/api/v1/models/nlp-sentiment/predict-batch",
            data="invalid",
            content_type="text/plain",
        )
        assert resp_inv.status_code == 400

    def test_predict_batch_internal_error(self, seeded_client: FlaskClient) -> None:
        from unittest.mock import patch

        patch_target = "app.services.registry_service.ModelRegistry.predict_batch"
        with patch(patch_target) as mock_pb:
            mock_pb.side_effect = RuntimeError("Batch computation error")
            resp = seeded_client.post(
                "/api/v1/models/nlp-sentiment/predict-batch",
                json={"inputs": [{"text": "hello"}]},
            )
            assert resp.status_code == 500
            assert "Batch inference failed" in resp.get_json()["error"]


class TestModelVersionManagementRoutes:
    """Tests for zero-downtime hot reloading endpoints."""

    def test_hot_swap_missing_version(self, seeded_client: FlaskClient) -> None:
        resp = seeded_client.post("/api/v1/models/nlp-sentiment/reload", json={})
        assert resp.status_code == 400
        assert "Target 'version' parameter is required" in resp.get_json()["error"]

    def test_hot_swap_unknown_version(self, seeded_client: FlaskClient) -> None:
        resp = seeded_client.post(
            "/api/v1/models/nlp-sentiment/reload", json={"version": "v999"}
        )
        assert resp.status_code == 404

    def test_hot_swap_runtime_error(self, seeded_client: FlaskClient) -> None:
        from unittest.mock import patch

        patch_target = "app.services.registry_service.ModelRegistry.hot_swap_version"
        with patch(patch_target) as mock_hs:
            mock_hs.side_effect = RuntimeError("Fatal disk corruption on model swap")
            resp = seeded_client.post(
                "/api/v1/models/nlp-sentiment/swap-version", json={"version": "v2"}
            )
            assert resp.status_code == 500
            assert "Version hot swap failed" in resp.get_json()["error"]

    def test_hot_swap_successful(
        self, seeded_client: FlaskClient, temp_dir: Path, test_db_path: Path
    ) -> None:
        # Create v2 artifact in models vault
        vault_dir = temp_dir / "models_vault"
        v2_path = vault_dir / "nlp-sentiment" / "v2" / "weights.json"
        v2_path.parent.mkdir(parents=True, exist_ok=True)
        v2_weights = {
            "model_id": "nlp-sentiment",
            "version": "v2",
            "classes": ["negative", "neutral", "positive"],
            "vocabulary": {"fantastic": 3.0, "horrible": -3.0},
            "bias": [0.1, 0.5, 0.1],
        }
        v2_path.write_text(json.dumps(v2_weights, indent=2), encoding="utf-8")

        # Register v2 in test database
        from app.db.connection import get_db_connection

        conn = get_db_connection(test_db_path)
        ModelVersionDAO.create(
            conn=conn,
            model_id="nlp-sentiment",
            version="v2",
            artifact_path=str(v2_path),
            input_schema={"text": "string"},
            output_schema={"sentiment": "string"},
            status="staging",
        )
        conn.close()

        # Trigger hot-swap via REST API endpoint
        resp = seeded_client.post(
            "/api/v1/models/nlp-sentiment/swap-version", json={"version": "v2"}
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        assert data["active_version"] == "v2"

        # Subsequent inference executes on v2
        pred_resp = seeded_client.post(
            "/api/v1/models/nlp-sentiment/predict", json={"text": "fantastic"}
        )
        assert pred_resp.status_code == 200
        pred_data = pred_resp.get_json()
        assert pred_data["version"] == "v2"
        assert pred_data["prediction"]["sentiment"] == "positive"


class TestMetricsAndHealthRoutes:
    """Tests for telemetry metrics, cache purging, and system health endpoints."""

    def test_metrics_endpoint_global(self, seeded_client: FlaskClient) -> None:
        # Execute prediction to generate telemetry
        seeded_client.post(
            "/api/v1/models/nlp-sentiment/predict",
            json={"text": "Great service!"},
        )

        resp = seeded_client.get("/api/v1/metrics")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        assert "global" in data
        assert "cache" in data
        assert "models" in data
        assert data["global"]["total_requests"] >= 1
        assert "p50" in data["global"]["latencies"]

    def test_metrics_endpoint_model_filter(self, seeded_client: FlaskClient) -> None:
        resp = seeded_client.get("/api/v1/telemetry?model_id=nlp-sentiment")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        assert data["model_id"] == "nlp-sentiment"
        assert "metrics" in data

    def test_metrics_reset_and_cache_clear(self, seeded_client: FlaskClient) -> None:
        # Populate cache and metrics
        seeded_client.post(
            "/api/v1/models/nlp-sentiment/predict",
            json={"text": "Testing metrics reset"},
        )

        # Clear cache
        resp_clear = seeded_client.post("/api/v1/cache/clear")
        assert resp_clear.status_code == 200
        assert resp_clear.get_json()["status"] == "success"

        # Reset metrics
        resp_reset = seeded_client.post("/api/v1/metrics/reset")
        assert resp_reset.status_code == 200
        assert resp_reset.get_json()["status"] == "success"

        # Verify global count reset to 0
        resp_metrics = seeded_client.get("/api/v1/metrics")
        assert resp_metrics.get_json()["global"]["total_requests"] == 0

    def test_enhanced_health_check(self, seeded_client: FlaskClient) -> None:
        resp = seeded_client.get("/api/health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "healthy"
        assert data["database"] == "connected"
        assert data["service"] == "pulseinfer-ml-api"
        assert "loaded_models_count" in data
        assert data["loaded_models_count"] == 3
        assert "nlp-sentiment" in data["loaded_models"]
        assert "cache" in data


def test_uninitialized_extensions_raise_runtime_error(app) -> None:
    from app.routes.metrics import _get_cache, _get_telemetry
    from app.routes.models import _get_registry

    with app.app_context():
        # Temporarily clear extensions
        app.extensions["registry"] = None
        app.extensions["telemetry"] = None
        app.extensions["cache"] = None

        with pytest.raises(RuntimeError) as exc_r:
            _get_registry()
        assert "ModelRegistry extension is not initialized" in str(exc_r.value)

        with pytest.raises(RuntimeError) as exc_t:
            _get_telemetry()
        assert "TelemetryEngine extension is not initialized" in str(exc_t.value)

        with pytest.raises(RuntimeError) as exc_c:
            _get_cache()
        assert "InferenceCache extension is not initialized" in str(exc_c.value)
