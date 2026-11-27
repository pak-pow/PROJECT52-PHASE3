"""Post analytics and engagement metrics HTTP routes for PulsePress."""

from flask import Blueprint, Response, current_app, jsonify, request

from app.db.connection import get_db_connection
from app.models.analytics import AnalyticsDAO
from app.models.comment import CommentDAO
from app.models.post import PostDAO

analytics_bp = Blueprint("analytics", __name__, url_prefix="/api/analytics")


@analytics_bp.route("/posts/<int:post_id>", methods=["GET"])
def get_post_analytics(post_id: int) -> tuple[Response, int]:
    """Return view counts, unique visitors, and comment engagement for a post."""
    with get_db_connection(current_app.config["DB_PATH"]) as conn:
        post = PostDAO.get_by_id(conn, post_id)
        if not post:
            return jsonify({"status": "error", "message": "Post not found."}), 404

        views = AnalyticsDAO.get_post_views(conn, post_id)
        unique_visitors = AnalyticsDAO.get_post_unique_visitors(conn, post_id)
        approved_comments = len(
            CommentDAO.list_for_post(conn, post_id, status="approved")
        )

    return (
        jsonify(
            {
                "status": "success",
                "data": {
                    "post_id": post["id"],
                    "slug": post["slug"],
                    "title": post["title"],
                    "view_count": views,
                    "unique_visitors": unique_visitors,
                    "approved_comments": approved_comments,
                    "reading_time_minutes": post.get("reading_time_minutes", 1),
                },
            }
        ),
        200,
    )


@analytics_bp.route("/top", methods=["GET"])
def get_top_posts() -> tuple[Response, int]:
    """Return top published posts ranked by total views."""
    try:
        limit = min(25, max(1, int(request.args.get("limit", 5))))
    except ValueError:
        limit = 5

    with get_db_connection(current_app.config["DB_PATH"]) as conn:
        top_posts = AnalyticsDAO.get_top_posts_by_views(conn, limit=limit)

    return jsonify({"status": "success", "data": {"posts": top_posts}}), 200
