"""Tag cloud and tag archive HTTP routes for PulsePress."""

import math

from flask import Blueprint, Response, current_app, jsonify, request

from app.db.connection import get_db_connection
from app.services.tag_service import TagService

tag_bp = Blueprint("tags", __name__, url_prefix="/api/tags")


@tag_bp.route("", methods=["GET"])
def list_tags() -> tuple[Response, int]:
    """Return tag cloud with normalized weights or full tag listing."""
    include_empty = request.args.get("include_empty", "false").lower() == "true"

    with get_db_connection(current_app.config["DB_PATH"]) as conn:
        cloud = TagService.generate_tag_cloud(conn, include_empty=include_empty)

    return jsonify({"status": "success", "data": {"tags": cloud}}), 200


@tag_bp.route("/<slug>/posts", methods=["GET"])
def get_posts_by_tag(slug: str) -> tuple[Response, int]:
    """Return paginated published posts associated with a tag slug."""
    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1

    max_ps = current_app.config.get("MAX_PAGE_SIZE", 50)
    default_ps = current_app.config.get("DEFAULT_PAGE_SIZE", 10)
    try:
        page_size = min(max_ps, max(1, int(request.args.get("page_size", default_ps))))
    except ValueError:
        page_size = default_ps

    with get_db_connection(current_app.config["DB_PATH"]) as conn:
        result = TagService.get_tag_with_posts(
            conn, slug=slug, page=page, page_size=page_size
        )

    if not result:
        return jsonify({"status": "error", "message": "Tag not found."}), 404

    tag, posts, total = result
    total_pages = max(1, math.ceil(total / page_size)) if total > 0 else 1

    return (
        jsonify(
            {
                "status": "success",
                "data": {
                    "tag": tag,
                    "posts": posts,
                    "total": total,
                    "page": page,
                    "page_size": page_size,
                    "total_pages": total_pages,
                },
            }
        ),
        200,
    )
