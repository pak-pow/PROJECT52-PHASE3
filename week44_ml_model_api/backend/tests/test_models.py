"""Unit tests for data access objects (ModelDAO, ModelVersionDAO, PredictionLogDAO)."""

from pathlib import Path

from app.db.connection import get_db_connection
from app.models.model_entity import ModelDAO
from app.models.model_version import ModelVersionDAO
from app.models.prediction_log import PredictionLogDAO


def test_model_dao_lifecycle(test_db_path: Path) -> None:
    """Verify complete CRUD lifecycle for registered models."""
    conn = get_db_connection(test_db_path)
    try:
        # Create model
        m = ModelDAO.create(
            conn=conn,
            model_id="nlp-test",
            name="Test NLP Model",
            domain="nlp",
            description="A test classifier",
            active_version="v1",
        )
        assert m["id"] == "nlp-test"
        assert m["name"] == "Test NLP Model"
        assert m["active_version"] == "v1"

        # Get by id
        fetched = ModelDAO.get_by_id(conn, "nlp-test")
        assert fetched is not None
        assert fetched["name"] == "Test NLP Model"

        # List all
        all_models = ModelDAO.list_all(conn)
        assert any(mod["id"] == "nlp-test" for mod in all_models)

        # Filter by domain
        nlp_models = ModelDAO.list_all(conn, domain="nlp")
        assert len(nlp_models) >= 1
        vision_models = ModelDAO.list_all(conn, domain="vision")
        assert len(vision_models) == 0

        # Update active version
        updated = ModelDAO.update_active_version(conn, "nlp-test", "v2")
        assert updated is True
        fetched_updated = ModelDAO.get_by_id(conn, "nlp-test")
        assert fetched_updated is not None
        assert fetched_updated["active_version"] == "v2"

        # Delete
        deleted = ModelDAO.delete(conn, "nlp-test")
        assert deleted is True
        assert ModelDAO.get_by_id(conn, "nlp-test") is None
    finally:
        conn.close()


def test_model_version_dao_lifecycle(test_db_path: Path) -> None:
    """Verify model version creation, status transitions, and queries."""
    conn = get_db_connection(test_db_path)
    try:
        ModelDAO.create(
            conn=conn,
            model_id="vision-test",
            name="Vision Test",
            domain="vision",
        )

        ver = ModelVersionDAO.create(
            conn=conn,
            model_id="vision-test",
            version="v1",
            artifact_path="/media/vault/weights.json",
            input_schema={"image": "string"},
            output_schema={"score": "float"},
            metrics={"accuracy": 0.95},
            status="active",
        )
        assert ver["version"] == "v1"
        assert ver["input_schema"]["image"] == "string"
        assert ver["metrics"]["accuracy"] == 0.95

        # Query
        fetched = ModelVersionDAO.get(conn, "vision-test", "v1")
        assert fetched is not None
        assert fetched["status"] == "active"

        # List versions
        v_list = ModelVersionDAO.list_by_model(conn, "vision-test")
        assert len(v_list) == 1

        # Update status
        st_updated = ModelVersionDAO.update_status(
            conn, "vision-test", "v1", "archived"
        )
        assert st_updated is True
        fetched_archived = ModelVersionDAO.get(conn, "vision-test", "v1")
        assert fetched_archived is not None
        assert fetched_archived["status"] == "archived"

        # Delete
        v_deleted = ModelVersionDAO.delete(conn, "vision-test", "v1")
        assert v_deleted is True
        assert ModelVersionDAO.get(conn, "vision-test", "v1") is None
    finally:
        conn.close()


def test_prediction_log_dao_lifecycle(test_db_path: Path) -> None:
    """Verify telemetry logging and metric aggregations."""
    conn = get_db_connection(test_db_path)
    try:
        # Check initial empty metrics
        empty_metrics = PredictionLogDAO.get_metrics_summary(conn)
        assert empty_metrics["total_requests"] == 0
        assert empty_metrics["avg_latency_ms"] == 0.0

        ModelDAO.create(
            conn=conn,
            model_id="tabular-test",
            name="Tabular Test",
            domain="tabular",
        )

        # Log prediction 1
        PredictionLogDAO.log_prediction(
            conn=conn,
            model_id="tabular-test",
            version="v1",
            batch_size=1,
            latency_ms=12.5,
            cached=False,
            status="success",
        )

        # Log prediction 2 (cached)
        PredictionLogDAO.log_prediction(
            conn=conn,
            model_id="tabular-test",
            version="v1",
            batch_size=4,
            latency_ms=1.2,
            cached=True,
            status="success",
        )

        # Log prediction 3 (error)
        PredictionLogDAO.log_prediction(
            conn=conn,
            model_id="tabular-test",
            version="v1",
            batch_size=1,
            latency_ms=8.0,
            cached=False,
            status="error",
            error_message="Shape mismatch",
        )

        # Query recent with model_id
        logs = PredictionLogDAO.get_recent(conn, model_id="tabular-test")
        assert len(logs) == 3
        assert logs[0]["status"] == "error"

        # Query recent without model_id (all models)
        all_logs = PredictionLogDAO.get_recent(conn, limit=10)
        assert len(all_logs) == 3

        # Aggregated summary without model_id
        global_summary = PredictionLogDAO.get_metrics_summary(conn)
        assert global_summary["total_requests"] == 3

        # Aggregated summary
        summary = PredictionLogDAO.get_metrics_summary(conn, model_id="tabular-test")
        assert summary["total_requests"] == 3
        assert summary["avg_latency_ms"] == 7.23
        assert summary["cache_hit_ratio"] == 0.3333
        assert summary["error_rate"] == 0.3333
    finally:
        conn.close()
