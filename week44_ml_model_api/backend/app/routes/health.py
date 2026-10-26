"""Health check endpoint for PulseInfer."""

from typing import Any, Dict, Tuple

from flask import Blueprint, current_app, jsonify

from app.db.connection import get_db_connection
from app.services.storage_service import StorageService

health_bp = Blueprint("health", __name__)


@health_bp.route("/api/health", methods=["GET"])
def health_check() -> Tuple[Any, int]:
    """Verify application database connectivity and storage vault status."""
    db_path = current_app.config.get("DB_PATH")
    vault_dir = current_app.config.get("MODELS_VAULT_DIR")
    storage = StorageService(vault_dir=vault_dir)

    db_status = "connected"
    try:
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT 1;")
        cursor.fetchone()
        conn.close()
    except Exception as exc:
        db_status = f"unhealthy: {exc}"
        return (
            jsonify(
                {
                    "status": "degraded",
                    "database": db_status,
                    "service": "pulseinfer-ml-api",
                }
            ),
            503,
        )

    vault_stats: Dict[str, Any] = storage.get_storage_stats()

    return (
        jsonify(
            {
                "status": "healthy",
                "database": db_status,
                "vault": vault_stats,
                "service": "pulseinfer-ml-api",
            }
        ),
        200,
    )
