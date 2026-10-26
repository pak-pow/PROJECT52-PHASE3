"""Unit tests for the seed script and default model registrations."""

from pathlib import Path

from app.db.connection import get_db_connection
from app.models.model_entity import ModelDAO
from app.models.model_version import ModelVersionDAO
from data.seed import seed_database


def test_seed_database_populates_models_and_artifacts(temp_dir: Path) -> None:
    """Verify seed script populates NLP, Vision, and Tabular models with weights."""
    db_file = temp_dir / "seeded.db"
    vault_dir = temp_dir / "models_vault"

    seed_database(db_path=db_file, vault_dir=vault_dir)

    conn = get_db_connection(db_file)
    try:
        models = ModelDAO.list_all(conn)
        model_ids = [m["id"] for m in models]

        assert "nlp-sentiment" in model_ids
        assert "vision-classifier" in model_ids
        assert "fraud-detector" in model_ids

        # Check versions
        v_nlp = ModelVersionDAO.get(conn, "nlp-sentiment", "v1")
        assert v_nlp is not None
        assert v_nlp["status"] == "active"
        assert Path(v_nlp["artifact_path"]).exists()

        v_vis = ModelVersionDAO.get(conn, "vision-classifier", "v1")
        assert v_vis is not None
        assert Path(v_vis["artifact_path"]).exists()

        v_fraud = ModelVersionDAO.get(conn, "fraud-detector", "v1")
        assert v_fraud is not None
        assert Path(v_fraud["artifact_path"]).exists()

        # Idempotency: Running seed again should succeed without duplicates
        seed_database(db_path=db_file, vault_dir=vault_dir)
        models_after = ModelDAO.list_all(conn)
        assert len(models_after) == 3
    finally:
        conn.close()
