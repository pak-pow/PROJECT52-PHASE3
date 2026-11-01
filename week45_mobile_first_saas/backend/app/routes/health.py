"""Health and system diagnostics route for PulseSub."""

import sqlite3
from datetime import datetime, timezone

from flask import Blueprint, current_app, jsonify

from app.config.settings import Config
from app.db.connection import get_db_connection

health_bp = Blueprint("health", __name__, url_prefix="/api")


@health_bp.route("/health", methods=["GET"])
def health_check():
    """System health check and database connectivity probe."""
    db_path = current_app.config.get("DB_PATH", Config.DB_PATH)
    db_status = "connected"

    try:
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT 1;")
        cursor.fetchone()
        cursor.close()
        conn.close()
    except sqlite3.Error as exc:
        db_status = f"unhealthy: {str(exc)}"
        return (
            jsonify(
                {
                    "status": "degraded",
                    "database": db_status,
                    "service": "PulseSub",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            ),
            503,
        )

    return (
        jsonify(
            {
                "status": "healthy",
                "database": db_status,
                "service": "PulseSub",
                "version": "1.0.0",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ),
        200,
    )
