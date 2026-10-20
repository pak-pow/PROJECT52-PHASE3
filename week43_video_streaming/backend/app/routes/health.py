"""Health check and diagnostics route."""

import shutil
from typing import Any, Dict, Tuple

from app.db.connection import get_db_connection
from app.services.storage_service import StorageService
from flask import Blueprint, jsonify

health_bp = Blueprint("health", __name__)


@health_bp.route("/api/health", methods=["GET"])
def health_check() -> Tuple[Any, int]:
    """Return platform operational status, storage stats, and database health."""
    db_status = "ok"
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        conn.close()
    except Exception as exc:
        db_status = f"unhealthy: {exc}"

    storage_stats: Dict[str, Any] = {}
    try:
        storage = StorageService()
        storage_stats = storage.get_storage_stats()
    except Exception as exc:
        storage_stats = {"error": str(exc)}

    payload = {
        "status": "ok" if db_status == "ok" else "degraded",
        "service": "PulseStream Video Streaming Platform",
        "version": "1.0.0",
        "database": db_status,
        "ffmpeg_available": bool(shutil.which("ffmpeg")),
        "storage": storage_stats,
    }
    status_code = 200 if db_status == "ok" else 503
    return jsonify(payload), status_code
