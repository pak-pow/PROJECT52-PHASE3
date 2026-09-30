from datetime import datetime
from flask import Blueprint, current_app, jsonify, request
from app.models.task_model import TaskModel

sync_bp = Blueprint("sync", __name__)


@sync_bp.route("/sync/batch", methods=["POST"])
def batch_sync():
    """
    Accepts an array of client offline mutations and applies them with
    Last-Write-Wins conflict resolution.
    """
    data = request.get_json(silent=True) or {}
    mutations = data.get("mutations")

    if not isinstance(mutations, list):
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Field 'mutations' must be an array of mutation objects",
                }
            ),
            400,
        )

    max_size = current_app.config.get("MAX_BATCH_SYNC_SIZE", 100)
    if len(mutations) > max_size:
        return (
            jsonify(
                {
                    "status": "error",
                    "message": f"Batch size exceeds maximum limit of {max_size}",
                }
            ),
            400,
        )

    result = TaskModel.batch_sync(mutations)
    server_time = datetime.utcnow().isoformat() + "Z"

    return (
        jsonify(
            {
                "status": "success",
                "processed": result["processed"],
                "applied": result["applied"],
                "conflicts": result["conflicts"],
                "server_time": server_time,
            }
        ),
        200,
    )


@sync_bp.route("/sync/delta", methods=["GET"])
def get_delta():
    """
    Returns tasks created, updated, or deleted since a given timestamp
    to bring the client cache in sync with the server.
    """
    since = request.args.get("since")
    delta_records = TaskModel.get_delta(since_timestamp=since)
    server_time = datetime.utcnow().isoformat() + "Z"

    return (
        jsonify(
            {
                "status": "success",
                "count": len(delta_records),
                "delta": delta_records,
                "server_time": server_time,
            }
        ),
        200,
    )
