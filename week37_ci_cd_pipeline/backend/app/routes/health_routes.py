import time
from flask import Blueprint, current_app, jsonify

health_bp = Blueprint("health_bp", __name__)
SERVICE_START_TIME = time.time()


@health_bp.route("/api/v1/health", methods=["GET"])
def health_check():
    """Health check endpoint used by CI/CD post-deploy smoke tests."""
    uptime_seconds = round(time.time() - SERVICE_START_TIME, 2)
    return (
        jsonify(
            {
                "status": "healthy",
                "service": current_app.config.get("APP_NAME", "Deployment Monitor"),
                "environment": current_app.config.get("ENV", "development"),
                "uptime_seconds": uptime_seconds,
                "version": current_app.config.get("APP_VERSION", "1.0.0"),
            }
        ),
        200,
    )


@health_bp.route("/api/v1/version", methods=["GET"])
def get_version():
    """Semantic version metadata and Git commit information."""
    return (
        jsonify(
            {
                "version": current_app.config.get("APP_VERSION", "1.0.0"),
                "commit_hash": current_app.config.get(
                    "GIT_COMMIT_HASH", "latest-commit"
                ),
                "build_number": current_app.config.get("BUILD_NUMBER", "dev-local"),
                "environment": current_app.config.get("ENV", "development"),
            }
        ),
        200,
    )
