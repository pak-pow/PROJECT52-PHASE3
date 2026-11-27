"""Threaded comment submission and admin moderation HTTP routes for PulsePress."""

from flask import Blueprint, Response, current_app, jsonify, request

from app.db.connection import get_db_connection
from app.models.post import PostDAO
from app.services.auth_service import require_auth
from app.services.comment_service import CommentService, RateLimitExceededError

comment_bp = Blueprint("comments", __name__)


@comment_bp.route("/api/posts/<slug>/comments", methods=["GET"])
def get_post_comments(slug: str) -> tuple[Response, int]:
    """Return approved threaded comment tree for a published post."""
    with get_db_connection(current_app.config["DB_PATH"]) as conn:
        post = PostDAO.get_by_slug(conn, slug)
        if not post or post["status"] != "published":
            return jsonify({"status": "error", "message": "Post not found."}), 404

        comments = CommentService.get_threaded_comments(
            conn, post["id"], status="approved"
        )

    return jsonify({"status": "success", "data": {"comments": comments}}), 200


@comment_bp.route("/api/posts/<slug>/comments", methods=["POST"])
def create_post_comment(slug: str) -> tuple[Response, int]:
    """Submit a new visitor comment (rate-limited by IP hash)."""
    payload = request.get_json(silent=True) or {}
    author_name = payload.get("author_name") or ""
    author_email = payload.get("author_email") or ""
    body = payload.get("body") or ""
    parent_id = payload.get("parent_id")
    ip_address = (
        request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or request.remote_addr
        or "127.0.0.1"
    )

    window_minutes = current_app.config.get("COMMENT_RATE_LIMIT_MINUTES", 10)
    max_comments = current_app.config.get("COMMENT_RATE_LIMIT_MAX", 5)

    with get_db_connection(current_app.config["DB_PATH"]) as conn:
        post = PostDAO.get_by_slug(conn, slug)
        if not post or post["status"] != "published":
            return jsonify({"status": "error", "message": "Post not found."}), 404

        try:
            comment = CommentService.submit_comment(
                conn=conn,
                post_id=post["id"],
                author_name=author_name,
                author_email=author_email,
                body=body,
                ip_address=ip_address,
                parent_id=parent_id,
                auto_approve=False,
                window_minutes=window_minutes,
                max_comments=max_comments,
            )
        except RateLimitExceededError as exc:
            return jsonify({"status": "error", "message": str(exc)}), 429
        except ValueError as exc:
            return jsonify({"status": "error", "message": str(exc)}), 400

    return jsonify({"status": "success", "data": {"comment": comment}}), 201


@comment_bp.route("/api/comments/queue", methods=["GET"])
@require_auth(roles=["admin"])
def list_comment_queue() -> tuple[Response, int]:
    """List comments filtered by moderation status for admin review."""
    status = request.args.get("status", "pending")
    try:
        limit = min(200, max(1, int(request.args.get("limit", 50))))
    except ValueError:
        limit = 50

    with get_db_connection(current_app.config["DB_PATH"]) as conn:
        try:
            comments = CommentService.list_moderation_queue(
                conn, status=status, limit=limit
            )
        except ValueError as exc:
            return jsonify({"status": "error", "message": str(exc)}), 400

    return jsonify({"status": "success", "data": {"comments": comments}}), 200


@comment_bp.route("/api/comments/<int:comment_id>/moderate", methods=["PUT"])
@require_auth(roles=["admin"])
def moderate_comment(comment_id: int) -> tuple[Response, int]:
    """Approve, reject, or flag a visitor comment (admin-only)."""
    payload = request.get_json(silent=True) or {}
    new_status = (payload.get("status") or "").strip()

    with get_db_connection(current_app.config["DB_PATH"]) as conn:
        try:
            updated = CommentService.moderate_comment(conn, comment_id, new_status)
        except ValueError as exc:
            msg = str(exc)
            code = 404 if "not found" in msg else 400
            return jsonify({"status": "error", "message": msg}), code

    return jsonify({"status": "success", "data": {"comment": updated}}), 200
