"""REST endpoints for querying asynchronous transcoding jobs."""

from typing import Any, Tuple

from flask import Blueprint, current_app, jsonify

from app.db.connection import get_db_connection
from app.models.job import TranscodingJobModel

job_bp = Blueprint("jobs", __name__, url_prefix="/api")


@job_bp.route("/jobs/<job_id>", methods=["GET"])
def get_job_status(job_id: str) -> Tuple[Any, int]:
    """Retrieve current transcoding progress, stage, and status for a job."""
    db_path = current_app.config.get("DB_PATH")
    conn = get_db_connection(db_path)
    try:
        job = TranscodingJobModel.get_by_id(conn, job_id)
        if not job:
            return jsonify({"error": "Transcoding job not found"}), 404
        return jsonify({"job": job}), 200
    finally:
        conn.close()


@job_bp.route("/jobs/video/<video_id>", methods=["GET"])
def get_job_for_video(video_id: str) -> Tuple[Any, int]:
    """Retrieve the most recent transcoding job associated with a video."""
    db_path = current_app.config.get("DB_PATH")
    conn = get_db_connection(db_path)
    try:
        job = TranscodingJobModel.get_by_video_id(conn, video_id)
        if not job:
            return jsonify({"error": "No transcoding job found for video"}), 404
        return jsonify({"job": job}), 200
    finally:
        conn.close()


@job_bp.route("/jobs/active", methods=["GET"])
def list_active_jobs() -> Tuple[Any, int]:
    """List all currently queued or processing transcoding tasks."""
    queue = getattr(current_app, "transcoding_queue", None)
    if queue:
        active = queue.list_active_jobs()
    else:
        db_path = current_app.config.get("DB_PATH")
        conn = get_db_connection(db_path)
        try:
            queued = TranscodingJobModel.list_by_status(conn, status="queued")
            processing = TranscodingJobModel.list_by_status(conn, status="processing")
            active = queued + processing
        finally:
            conn.close()

    return jsonify({"jobs": active, "count": len(active)}), 200
