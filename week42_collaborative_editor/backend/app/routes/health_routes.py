"""Health check route for PulsePad."""

from flask import Blueprint, jsonify

health_bp = Blueprint("health", __name__)


@health_bp.route("/health", methods=["GET"])
def health_check():
    """Return application health status."""
    return (
        jsonify(
            {
                "status": "healthy",
                "service": "PulsePad Collaborative Editor",
                "version": "1.0.0",
            }
        ),
        200,
    )
