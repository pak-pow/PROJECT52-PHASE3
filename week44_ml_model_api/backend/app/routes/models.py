"""REST API routes for model inference, catalog inspection, and version management."""

import sqlite3
from typing import Any, List, Optional, Tuple

from flask import Blueprint, current_app, jsonify, request

from app.db.connection import get_db_connection
from app.models.model_entity import ModelDAO
from app.models.model_version import ModelVersionDAO
from app.services.registry_service import ModelRegistry

models_bp = Blueprint("models", __name__, url_prefix="/api/v1/models")


def _get_registry() -> ModelRegistry:
    """Retrieve active ModelRegistry extension instance from current application."""
    registry = current_app.extensions.get("registry")
    if not registry or not isinstance(registry, ModelRegistry):
        raise RuntimeError("ModelRegistry extension is not initialized")
    return registry


def _get_conn() -> sqlite3.Connection:
    """Acquire database connection from application configured DB_PATH."""
    db_path = current_app.config.get("DB_PATH")
    return get_db_connection(db_path)


@models_bp.route("", methods=["GET"])
def list_models() -> Tuple[Any, int]:
    """List all registered models with schemas, active versions, and health status."""
    registry = _get_registry()
    domain = request.args.get("domain")

    conn = _get_conn()
    try:
        models = registry.list_models(domain=domain, conn=conn)
        return (
            jsonify(
                {
                    "status": "success",
                    "count": len(models),
                    "domain_filter": domain,
                    "models": models,
                }
            ),
            200,
        )
    finally:
        conn.close()


@models_bp.route("/<model_id>", methods=["GET"])
def get_model(model_id: str) -> Tuple[Any, int]:
    """Retrieve detailed runtime state and telemetry for a specific model."""
    registry = _get_registry()
    clean_id = model_id.strip().lower()

    conn = _get_conn()
    try:
        status = registry.get_model_status(clean_id, conn=conn)
        return jsonify({"status": "success", "model": status}), 200
    except KeyError:
        return (
            jsonify({"status": "error", "error": f"Model '{clean_id}' not found"}),
            404,
        )
    finally:
        conn.close()


@models_bp.route("/<model_id>/metadata", methods=["GET"])
def get_model_metadata(model_id: str) -> Tuple[Any, int]:
    """Retrieve input/output schemas, metrics, and all available version records."""
    clean_id = model_id.strip().lower()
    conn = _get_conn()
    try:
        model_rec = ModelDAO.get_by_id(conn, clean_id)
        if not model_rec:
            return (
                jsonify({"status": "error", "error": f"Model '{clean_id}' not found"}),
                404,
            )

        versions = ModelVersionDAO.list_by_model(conn, clean_id)
        active_ver = model_rec["active_version"]
        active_rec = next((v for v in versions if v["version"] == active_ver), None)

        return (
            jsonify(
                {
                    "status": "success",
                    "model_id": clean_id,
                    "name": model_rec["name"],
                    "domain": model_rec["domain"],
                    "description": model_rec.get("description"),
                    "active_version": active_ver,
                    "input_schema": (active_rec or {}).get("input_schema", {}),
                    "output_schema": (active_rec or {}).get("output_schema", {}),
                    "metrics": (active_rec or {}).get("metrics", {}),
                    "versions": versions,
                }
            ),
            200,
        )
    finally:
        conn.close()


@models_bp.route("/<model_id>/predict", methods=["POST"])
def predict_single(model_id: str) -> Tuple[Any, int]:
    """Execute single-item model inference with schema validation and caching."""
    registry = _get_registry()
    clean_id = model_id.strip().lower()

    payload = request.get_json(silent=True)
    if payload is None:
        return (
            jsonify(
                {
                    "status": "error",
                    "error": "Request body must be a valid JSON object",
                }
            ),
            400,
        )

    use_cache_str = request.args.get("use_cache", "true").strip().lower()
    use_cache = use_cache_str in ("true", "1", "yes")

    use_batcher_str = request.args.get("use_batcher", "true").strip().lower()
    use_batcher = use_batcher_str in ("true", "1", "yes")

    raw_timeout = request.args.get("timeout")
    timeout = float(raw_timeout) if raw_timeout else None

    conn = _get_conn()
    try:
        result = registry.predict(
            model_id=clean_id,
            payload=payload,
            use_cache=use_cache,
            use_batcher=use_batcher,
            timeout=timeout,
            conn=conn,
        )
        return jsonify(result), 200

    except KeyError as exc:
        return jsonify({"status": "error", "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"status": "error", "error": str(exc)}), 400
    except TimeoutError as exc:
        return jsonify({"status": "error", "error": str(exc)}), 504
    except Exception as exc:
        return (
            jsonify({"status": "error", "error": f"Inference execution failed: {exc}"}),
            500,
        )
    finally:
        conn.close()


@models_bp.route("/<model_id>/predict-batch", methods=["POST"])
def predict_batch(model_id: str) -> Tuple[Any, int]:
    """Execute vectorized batch inference directly on a collection of inputs."""
    registry = _get_registry()
    clean_id = model_id.strip().lower()

    data = request.get_json(silent=True)
    if data is None:
        return (
            jsonify(
                {
                    "status": "error",
                    "error": "Request body must be a valid JSON payload",
                }
            ),
            400,
        )

    inputs: Optional[List[Any]] = None
    if isinstance(data, list):
        inputs = data
    elif isinstance(data, dict):
        inputs = data.get("inputs") or data.get("batch")

    if not inputs or not isinstance(inputs, list):
        return (
            jsonify(
                {
                    "status": "error",
                    "error": (
                        "Request body must contain a non-empty 'inputs' list "
                        "or JSON array"
                    ),
                }
            ),
            400,
        )

    conn = _get_conn()
    try:
        predictions = registry.predict_batch(
            model_id=clean_id,
            batch_payload=inputs,
            conn=conn,
        )
        status = registry.get_model_status(clean_id, conn=conn)

        return (
            jsonify(
                {
                    "status": "success",
                    "model_id": clean_id,
                    "version": status.get("active_version", "v1"),
                    "batch_size": len(inputs),
                    "predictions": predictions,
                }
            ),
            200,
        )
    except KeyError as exc:
        return jsonify({"status": "error", "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"status": "error", "error": str(exc)}), 400
    except Exception as exc:
        return (
            jsonify({"status": "error", "error": f"Batch inference failed: {exc}"}),
            500,
        )
    finally:
        conn.close()


@models_bp.route("/<model_id>/reload", methods=["POST"])
@models_bp.route("/<model_id>/swap-version", methods=["POST"])
def swap_model_version(model_id: str) -> Tuple[Any, int]:
    """Trigger zero-downtime hot swap to a specified target version."""
    registry = _get_registry()
    clean_id = model_id.strip().lower()

    data = request.get_json(silent=True) or {}
    target_version = (data.get("version") or request.args.get("version") or "").strip()

    if not target_version:
        return (
            jsonify(
                {"status": "error", "error": "Target 'version' parameter is required"}
            ),
            400,
        )

    conn = _get_conn()
    try:
        registry.hot_swap_version(
            model_id=clean_id,
            new_version=target_version,
            conn=conn,
        )
        return (
            jsonify(
                {
                    "status": "success",
                    "model_id": clean_id,
                    "active_version": target_version,
                    "message": (
                        f"Model '{clean_id}' successfully hot-swapped to "
                        f"version '{target_version}'"
                    ),
                }
            ),
            200,
        )
    except KeyError as exc:
        return jsonify({"status": "error", "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"status": "error", "error": str(exc)}), 404
    except Exception as exc:
        return (
            jsonify({"status": "error", "error": f"Version hot swap failed: {exc}"}),
            500,
        )
    finally:
        conn.close()
