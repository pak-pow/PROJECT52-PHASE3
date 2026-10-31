"""REST API routes for latency telemetry, percentile metrics, and cache management."""

from typing import Any, Tuple

from flask import Blueprint, current_app, jsonify, request

from app.db.connection import get_db_connection
from app.models.prediction_log import PredictionLogDAO
from app.services.cache_service import InferenceCache
from app.services.telemetry_service import TelemetryEngine

metrics_bp = Blueprint("metrics", __name__, url_prefix="/api/v1")


def _get_telemetry() -> TelemetryEngine:
    """Retrieve active TelemetryEngine extension instance from application."""
    telemetry = current_app.extensions.get("telemetry")
    if not telemetry or not isinstance(telemetry, TelemetryEngine):
        raise RuntimeError("TelemetryEngine extension is not initialized")
    return telemetry


def _get_cache() -> InferenceCache:
    """Retrieve active InferenceCache extension instance from application."""
    cache = current_app.extensions.get("cache")
    if not cache or not isinstance(cache, InferenceCache):
        raise RuntimeError("InferenceCache extension is not initialized")
    return cache


@metrics_bp.route("/metrics", methods=["GET"])
@metrics_bp.route("/telemetry", methods=["GET"])
def get_metrics() -> Tuple[Any, int]:
    """Retrieve system-wide and per-model latency percentiles and cache telemetry."""
    telemetry = _get_telemetry()
    cache = _get_cache()

    model_id = request.args.get("model_id")
    if model_id:
        clean_id = model_id.strip().lower()
        model_metrics = telemetry.get_model_metrics(clean_id)
        return (
            jsonify(
                {
                    "status": "success",
                    "model_id": clean_id,
                    "metrics": model_metrics,
                }
            ),
            200,
        )

    global_metrics = telemetry.get_global_metrics()
    cache_stats = cache.get_stats()
    all_models = telemetry.get_all_models_metrics()

    return (
        jsonify(
            {
                "status": "success",
                "global": global_metrics,
                "cache": cache_stats,
                "models": all_models,
            }
        ),
        200,
    )


@metrics_bp.route("/metrics/reset", methods=["POST"])
def reset_metrics() -> Tuple[Any, int]:
    """Reset latency sliding windows, counter statistics, and cache metrics."""
    telemetry = _get_telemetry()
    cache = _get_cache()

    telemetry.reset()
    cache.reset_stats()

    return (
        jsonify(
            {
                "status": "success",
                "message": "Telemetry metrics and cache stats reset successfully",
            }
        ),
        200,
    )


@metrics_bp.route("/cache/clear", methods=["POST"])
def clear_cache() -> Tuple[Any, int]:
    """Purge all entries from the in-memory prediction cache."""
    cache = _get_cache()
    cache.clear()

    return (
        jsonify(
            {
                "status": "success",
                "message": "Inference cache cleared successfully",
            }
        ),
        200,
    )


@metrics_bp.route("/logs", methods=["GET"])
def get_prediction_logs() -> Tuple[Any, int]:
    """Retrieve recent inference execution logs for observability."""
    model_id = request.args.get("model_id")
    raw_limit = request.args.get("limit", "50")
    try:
        limit = min(max(1, int(raw_limit)), 200)
    except ValueError:
        limit = 50

    db_path = current_app.config.get("DB_PATH")
    conn = get_db_connection(db_path)
    try:
        logs = PredictionLogDAO.get_recent(conn, model_id=model_id, limit=limit)
        return jsonify({"status": "success", "count": len(logs), "logs": logs}), 200
    finally:
        conn.close()
