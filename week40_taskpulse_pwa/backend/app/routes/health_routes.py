from datetime import datetime
from flask import Blueprint, jsonify

health_bp = Blueprint("health", __name__)


@health_bp.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint for container and client probes."""
    return (
        jsonify(
            {
                "status": "healthy",
                "service": "TaskPulse PWA API",
                "timestamp": datetime.utcnow().isoformat() + "Z",
            }
        ),
        200,
    )


@health_bp.route("/version", methods=["GET"])
def version_check():
    """Version and feature specification endpoint."""
    return (
        jsonify(
            {
                "version": "1.0.0",
                "service": "TaskPulse PWA API",
                "pwa_sync_protocol": "v1",
            }
        ),
        200,
    )
