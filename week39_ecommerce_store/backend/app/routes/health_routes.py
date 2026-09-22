from datetime import datetime, timezone

from flask import Blueprint, current_app, jsonify

from app.db import ping_db

health_bp = Blueprint("health", __name__, url_prefix="/api/v1")


@health_bp.route("/health", methods=["GET"])
def health_check():
    return jsonify(
        {
            "status": "healthy",
            "service": "shoppulse-backend",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "environment": current_app.config.get("ENV", "development"),
        }
    )


@health_bp.route("/version", methods=["GET"])
def version():
    return jsonify(
        {
            "service": "shoppulse-backend",
            "version": current_app.config.get("APP_VERSION", "1.0.0"),
            "git_commit": current_app.config.get("GIT_COMMIT", "unknown"),
        }
    )


@health_bp.route("/ready", methods=["GET"])
def readiness():
    is_ok, latency = ping_db()
    if is_ok:
        return (
            jsonify(
                {
                    "status": "ready",
                    "database": "connected",
                    "latency_ms": latency,
                }
            ),
            200,
        )

    return (
        jsonify(
            {
                "status": "unready",
                "database": "disconnected",
                "latency_ms": latency,
            }
        ),
        503,
    )
