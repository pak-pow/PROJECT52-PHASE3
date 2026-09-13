"""Health, version, and readiness probe endpoints."""

import time
from datetime import datetime, timezone

from flask import Blueprint, current_app, jsonify

from app.cache import cache
from app.db import check_db_health

health_bp = Blueprint("health", __name__)
_START_TIME = time.time()


@health_bp.route("/health", methods=["GET"])
def health_check():
    """Liveness probe returning application uptime, hostname, and status."""
    config = current_app.config
    uptime = round(time.time() - _START_TIME, 2)
    return (
        jsonify(
            {
                "status": "healthy",
                "service": "docker-pulse-api",
                "uptime_seconds": uptime,
                "environment": config.get("ENVIRONMENT", "development"),
                "hostname": config.get("HOSTNAME", "unknown"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ),
        200,
    )


@health_bp.route("/version", methods=["GET"])
def version():
    """Service version and git build metadata."""
    config = current_app.config
    return (
        jsonify(
            {
                "version": config.get("VERSION", "1.0.0"),
                "app_name": config.get("APP_NAME", "Docker Pulse Task Ops Hub"),
                "commit_sha": config.get("COMMIT_SHA", "unknown"),
                "build_number": config.get("BUILD_NUMBER", "local-dev"),
            }
        ),
        200,
    )


@health_bp.route("/ready", methods=["GET"])
def readiness():
    """Readiness probe evaluating database and cache dependencies."""
    db_health = check_db_health(current_app.config.get("DATABASE_URL"))
    cache_health = cache.check_health()

    is_ready = (
        db_health.get("status") == "healthy" and cache_health.get("status") == "healthy"
    )

    status_code = 200 if is_ready else 503
    return (
        jsonify(
            {
                "status": "ready" if is_ready else "degraded",
                "database": db_health,
                "cache": cache_health,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ),
        status_code,
    )
