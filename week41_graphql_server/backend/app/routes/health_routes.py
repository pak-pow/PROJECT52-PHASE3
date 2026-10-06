from datetime import datetime

from flask import Blueprint, jsonify

health_bp = Blueprint("health", __name__)


@health_bp.route("/api/health", methods=["GET"])
def health_check():
    """Health check endpoint for container and client probes."""
    return (
        jsonify(
            {
                "status": "healthy",
                "service": "PulseGraph GraphQL API",
                "timestamp": datetime.utcnow().isoformat() + "Z",
            }
        ),
        200,
    )


@health_bp.route("/api/version", methods=["GET"])
def version_check():
    """Version and specification endpoint."""
    return (
        jsonify(
            {
                "version": "1.0.0",
                "service": "PulseGraph GraphQL API",
                "graphql_engine": "graphene 3.4 / graphql-core 3.2",
            }
        ),
        200,
    )
