"""Health check endpoint for PulsePress service."""

from app.db.connection import get_db_connection
from flask import Blueprint, jsonify

health_bp = Blueprint("health", __name__)


@health_bp.route("/api/health", methods=["GET"])
def health_check():
    """Verify backend and database connectivity status."""
    db_status = "disconnected"
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1;")
        res = cursor.fetchone()
        if res and res[0] == 1:
            db_status = "connected"
        conn.close()
    except Exception as exc:  # noqa: B902
        db_status = f"error: {str(exc)}"

    return (
        jsonify(
            {
                "status": "healthy" if db_status == "connected" else "degraded",
                "service": "PulsePress",
                "database": db_status,
                "version": "1.0.0",
            }
        ),
        200 if db_status == "connected" else 503,
    )
