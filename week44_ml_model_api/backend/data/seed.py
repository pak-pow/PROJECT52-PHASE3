"""Seed script initializing default models and versions in PulseInfer."""

import json
import sys
from pathlib import Path
from typing import Optional, Union

# Ensure backend package is in python search path
CURRENT_DIR = Path(__file__).resolve().parent.parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from app.config.settings import Config  # noqa: E402
from app.db.connection import get_db_connection, init_db  # noqa: E402
from app.models.model_entity import ModelDAO  # noqa: E402
from app.models.model_version import ModelVersionDAO  # noqa: E402
from app.services.storage_service import StorageService  # noqa: E402


def seed_database(
    db_path: Optional[Union[str, Path]] = None,
    vault_dir: Optional[Union[str, Path]] = None,
) -> None:
    """Populate database with default models and seed artifact weights."""
    target_db = db_path or Config.DB_PATH
    storage = StorageService(vault_dir=vault_dir or Config.MODELS_VAULT_DIR)
    storage.ensure_storage_dirs()

    # Initialize tables if not already present
    init_db(db_path=target_db)
    conn = get_db_connection(target_db)

    try:
        # Model 1: NLP Sentiment & Intent
        m1_id = "nlp-sentiment"
        if not ModelDAO.get_by_id(conn, m1_id):
            ModelDAO.create(
                conn=conn,
                model_id=m1_id,
                name="PulseText Sentiment & Intent Analyzer",
                domain="nlp",
                description=(
                    "Subword vocabulary and Softmax classifier for sentiment "
                    "and intent detection."
                ),
                active_version="v1",
            )

        # Artifact weights for NLP v1
        v1_path = storage.get_artifact_path(m1_id, "v1", "weights.json")
        v1_weights = {
            "model_id": m1_id,
            "version": "v1",
            "classes": ["negative", "neutral", "positive"],
            "vocabulary": {
                "great": 1.5,
                "excellent": 2.0,
                "good": 1.2,
                "love": 1.8,
                "fast": 1.1,
                "poor": -1.5,
                "bad": -1.8,
                "terrible": -2.2,
                "slow": -1.0,
                "error": -1.4,
            },
            "bias": [0.1, 0.5, 0.1],
        }
        v1_path.write_text(json.dumps(v1_weights, indent=2), encoding="utf-8")

        if not ModelVersionDAO.get(conn, m1_id, "v1"):
            ModelVersionDAO.create(
                conn=conn,
                model_id=m1_id,
                version="v1",
                artifact_path=str(v1_path),
                input_schema={"text": "string"},
                output_schema={
                    "sentiment": "string",
                    "confidence": "float",
                    "probabilities": "dict",
                },
                metrics={"accuracy": 0.942, "f1_score": 0.938},
                status="active",
            )

        # Artifact weights for NLP v2-rc1 (hot-swap candidate)
        v1_2_path = storage.get_artifact_path(m1_id, "v2-rc1", "weights.json")
        v1_2_weights = {
            "model_id": m1_id,
            "version": "v2-rc1",
            "classes": ["negative", "neutral", "positive"],
            "vocabulary": {
                "great": 1.8,
                "excellent": 2.2,
                "good": 1.4,
                "love": 2.0,
                "fast": 1.3,
                "poor": -1.7,
                "bad": -2.0,
                "terrible": -2.5,
                "slow": -1.2,
                "error": -1.6,
                "exceptional": 2.5,
                "flawless": 2.3,
                "horrible": -2.7,
            },
            "bias": [0.05, 0.4, 0.05],
        }
        v1_2_path.write_text(json.dumps(v1_2_weights, indent=2), encoding="utf-8")

        if not ModelVersionDAO.get(conn, m1_id, "v2-rc1"):
            ModelVersionDAO.create(
                conn=conn,
                model_id=m1_id,
                version="v2-rc1",
                artifact_path=str(v1_2_path),
                input_schema={"text": "string"},
                output_schema={
                    "sentiment": "string",
                    "confidence": "float",
                    "probabilities": "dict",
                },
                metrics={"accuracy": 0.965, "f1_score": 0.961},
                status="inactive",
            )

        # Model 2: Computer Vision Classifier
        m2_id = "vision-classifier"
        if not ModelDAO.get_by_id(conn, m2_id):
            ModelDAO.create(
                conn=conn,
                model_id=m2_id,
                name="PulseVision Image Feature Classifier",
                domain="vision",
                description=(
                    "Normalized tensor projection network classifying image "
                    "content and visual quality."
                ),
                active_version="v1",
            )

        v2_path = storage.get_artifact_path(m2_id, "v1", "weights.json")
        v2_weights = {
            "model_id": m2_id,
            "version": "v1",
            "target_size": [32, 32],
            "channels": 3,
            "classes": ["landscape", "document", "portrait", "product"],
            "projection_weights": [[0.25, -0.1, 0.05, 0.3]],
        }
        v2_path.write_text(json.dumps(v2_weights, indent=2), encoding="utf-8")

        if not ModelVersionDAO.get(conn, m2_id, "v1"):
            ModelVersionDAO.create(
                conn=conn,
                model_id=m2_id,
                version="v1",
                artifact_path=str(v2_path),
                input_schema={"image_base64": "string"},
                output_schema={
                    "top_class": "string",
                    "confidence": "float",
                    "class_scores": "dict",
                },
                metrics={"top1_accuracy": 0.915, "top5_accuracy": 0.982},
                status="active",
            )

        # Model 3: Tabular Fraud Detector
        m3_id = "fraud-detector"
        if not ModelDAO.get_by_id(conn, m3_id):
            ModelDAO.create(
                conn=conn,
                model_id=m3_id,
                name="PulseRisk Tabular Fraud Scorer",
                domain="tabular",
                description=(
                    "Calibrated decision boundary model computing transaction "
                    "risk and anomaly scores."
                ),
                active_version="v1",
            )

        v3_path = storage.get_artifact_path(m3_id, "v1", "weights.json")
        v3_weights = {
            "model_id": m3_id,
            "version": "v1",
            "features": [
                "transaction_amount",
                "user_age",
                "velocity_1h",
                "is_foreign",
            ],
            "coefficients": [0.005, -0.02, 0.35, 1.2],
            "intercept": -1.8,
            "threshold": 0.5,
        }
        v3_path.write_text(json.dumps(v3_weights, indent=2), encoding="utf-8")

        if not ModelVersionDAO.get(conn, m3_id, "v1"):
            ModelVersionDAO.create(
                conn=conn,
                model_id=m3_id,
                version="v1",
                artifact_path=str(v3_path),
                input_schema={
                    "transaction_amount": "float",
                    "user_age": "int",
                    "velocity_1h": "int",
                    "is_foreign": "int",
                },
                output_schema={
                    "risk_score": "float",
                    "is_flagged": "bool",
                    "risk_level": "string",
                },
                metrics={"roc_auc": 0.967, "precision": 0.924, "recall": 0.891},
                status="active",
            )

    finally:
        conn.close()


if __name__ == "__main__":
    seed_database()
    print("PulseInfer seed data initialized successfully.")
