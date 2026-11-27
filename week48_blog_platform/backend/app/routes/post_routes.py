"""Blog post CRUD, publishing, and reader HTTP routes for PulsePress."""

import hashlib
import json
import math
from contextlib import closing
from typing import Any, Dict, List, Tuple

from flask import Blueprint, Response, current_app, g, jsonify, request

from app.content.markdown_engine import MarkdownEngine
from app.db.connection import get_db_connection
from app.models.analytics import AnalyticsDAO
from app.models.post import PostDAO
from app.models.tag import TagDAO
from app.services.auth_service import AuthService, require_auth
from app.services.search_engine import SearchEngine
from app.services.tag_service import TagService

post_bp = Blueprint("posts", __name__, url_prefix="/api/posts")


def _parse_pagination() -> Tuple[int, int]:
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
    return page, page_size


def _visitor_fingerprint() -> str:
    explicit = request.headers.get("X-Visitor-Hash", "").strip()
    if explicit:
        return explicit[:64]
    ip = request.remote_addr or "127.0.0.1"
    ua = request.headers.get("User-Agent", "unknown")
    return hashlib.sha256(f"{ip}:{ua}".encode("utf-8")).hexdigest()


def _index_post_record(conn: Any, post: Dict[str, Any]) -> None:
    tag_names = [t["name"] for t in post.get("tags", [])]
    SearchEngine().index_post(
        conn,
        post["id"],
        post["title"],
        post["body_markdown"],
        tag_names,
    )


def _format_post_response(post: Dict[str, Any]) -> Dict[str, Any]:
    formatted = dict(post)
    raw_toc = formatted.get("toc_json") or "[]"
    try:
        formatted["toc"] = json.loads(raw_toc) if isinstance(raw_toc, str) else raw_toc
    except Exception:
        formatted["toc"] = []
    return formatted


@post_bp.route("", methods=["GET"])
def list_posts() -> tuple[Response, int]:
    """List paginated posts filtered by status, tag slug, and sort order."""
    page, page_size = _parse_pagination()
    tag_slug = request.args.get("tag")
    order_by = request.args.get("order_by", "published_at_desc")
    requested_status = request.args.get("status", "published")

    with closing(get_db_connection(current_app.config["DB_PATH"])) as conn:
        user = AuthService.resolve_optional_user(conn)
        if requested_status != "published":
            if not user or user.get("role") not in ("admin", "author"):
                effective_status = "published"
                author_id = None
            else:
                effective_status = (
                    None if requested_status == "all" else requested_status
                )
                author_id = None if user.get("role") == "admin" else user["id"]
        else:
            effective_status = "published"
            author_id = None

        posts, total = PostDAO.list_posts(
            conn,
            status=effective_status,
            tag_slug=tag_slug,
            author_id=author_id,
            page=page,
            page_size=page_size,
            order_by=order_by,
        )

    total_pages = max(1, math.ceil(total / page_size)) if total > 0 else 1
    return (
        jsonify(
            {
                "status": "success",
                "data": {
                    "posts": [_format_post_response(p) for p in posts],
                    "total": total,
                    "page": page,
                    "page_size": page_size,
                    "total_pages": total_pages,
                },
            }
        ),
        200,
    )


@post_bp.route("/<slug>", methods=["GET"])
def get_post(slug: str) -> tuple[Response, int]:
    """Retrieve a single post with rendered HTML, TOC, view count, and related posts."""
    with closing(get_db_connection(current_app.config["DB_PATH"])) as conn:
        post = PostDAO.get_by_slug(conn, slug)
        if not post:
            return jsonify({"status": "error", "message": "Post not found."}), 404

        if post["status"] != "published":
            user = AuthService.resolve_optional_user(conn)
            is_owner = user and (
                user["role"] == "admin" or user["id"] == post["author_id"]
            )
            if not is_owner:
                return jsonify({"status": "error", "message": "Post not found."}), 404
        else:
            AnalyticsDAO.record_view(conn, post["id"], _visitor_fingerprint())

        view_count = AnalyticsDAO.get_post_views(conn, post["id"])
        related = TagService.find_related_posts(conn, post["id"], limit=4)

    formatted = _format_post_response(post)
    formatted["view_count"] = view_count
    formatted["related_posts"] = [_format_post_response(r) for r in related]

    return jsonify({"status": "success", "data": {"post": formatted}}), 200


@post_bp.route("", methods=["POST"])
@require_auth(roles=["admin", "author"])
def create_post() -> tuple[Response, int]:
    """Create a new blog post from Markdown content."""
    payload = request.get_json(silent=True) or {}
    title = (payload.get("title") or "").strip()
    body_markdown = payload.get("body_markdown") or ""
    excerpt = payload.get("excerpt") or ""
    featured_image = payload.get("featured_image") or ""
    status = payload.get("status", "draft")
    raw_tags = payload.get("tags") or []

    if not title:
        return jsonify({"status": "error", "message": "Post title is required."}), 400
    if not body_markdown.strip():
        return (
            jsonify({"status": "error", "message": "Markdown body is required."}),
            400,
        )
    if status not in ("draft", "published", "archived"):
        return jsonify({"status": "error", "message": "Invalid post status."}), 400

    engine = MarkdownEngine(wpm=current_app.config.get("WORDS_PER_MINUTE", 200))
    processed = engine.process(body_markdown)
    final_excerpt = excerpt or processed["excerpt"]

    with closing(get_db_connection(current_app.config["DB_PATH"])) as conn:
        tag_ids: List[int] = []
        if isinstance(raw_tags, list) and raw_tags:
            if all(isinstance(t, int) for t in raw_tags):
                tag_ids = raw_tags
            else:
                resolved = TagService.get_or_create_tags(
                    conn, [str(t) for t in raw_tags]
                )
                tag_ids = [t["id"] for t in resolved]

        created = PostDAO.create(
            conn=conn,
            author_id=g.current_user["id"],
            title=title,
            body_markdown=body_markdown,
            body_html=processed["body_html"],
            excerpt=final_excerpt,
            featured_image=featured_image,
            status=status,
            reading_time_minutes=processed["reading_time_minutes"],
            toc_json=processed["toc_json"],
            tag_ids=tag_ids,
        )

        if created["status"] == "published":
            _index_post_record(conn, created)

    return (
        jsonify(
            {"status": "success", "data": {"post": _format_post_response(created)}}
        ),
        201,
    )


@post_bp.route("/<slug>", methods=["PUT"])
@require_auth(roles=["admin", "author"])
def update_post(slug: str) -> tuple[Response, int]:
    """Update an existing post's content, status, or taxonomy tags."""
    payload = request.get_json(silent=True) or {}

    with closing(get_db_connection(current_app.config["DB_PATH"])) as conn:
        existing = PostDAO.get_by_slug(conn, slug)
        if not existing:
            return jsonify({"status": "error", "message": "Post not found."}), 404

        if (
            g.current_user["role"] != "admin"
            and existing["author_id"] != g.current_user["id"]
        ):
            return (
                jsonify({"status": "error", "message": "Permission denied."}),
                403,
            )

        updates: Dict[str, Any] = {}
        if "title" in payload and payload["title"].strip():
            updates["title"] = payload["title"].strip()
        if "featured_image" in payload:
            updates["featured_image"] = payload["featured_image"]
        if "status" in payload:
            if payload["status"] not in ("draft", "published", "archived"):
                return (
                    jsonify({"status": "error", "message": "Invalid post status."}),
                    400,
                )
            updates["status"] = payload["status"]

        if "body_markdown" in payload:
            body_md = payload["body_markdown"]
            engine = MarkdownEngine(wpm=current_app.config.get("WORDS_PER_MINUTE", 200))
            processed = engine.process(body_md)
            updates["body_markdown"] = body_md
            updates["body_html"] = processed["body_html"]
            updates["excerpt"] = payload.get("excerpt") or processed["excerpt"]
            updates["reading_time_minutes"] = processed["reading_time_minutes"]
            updates["toc_json"] = processed["toc_json"]
        elif "excerpt" in payload:
            updates["excerpt"] = payload["excerpt"]

        if "tags" in payload and isinstance(payload["tags"], list):
            raw_tags = payload["tags"]
            if all(isinstance(t, int) for t in raw_tags):
                updates["tag_ids"] = raw_tags
            else:
                resolved = TagService.get_or_create_tags(
                    conn, [str(t) for t in raw_tags]
                )
                updates["tag_ids"] = [t["id"] for t in resolved]

        updated = PostDAO.update(conn, existing["id"], **updates)
        if updated and updated["status"] == "published":
            _index_post_record(conn, updated)
        else:
            SearchEngine().remove_post_from_index(conn, existing["id"])

    return (
        jsonify(
            {"status": "success", "data": {"post": _format_post_response(updated)}}
        ),
        200,
    )


@post_bp.route("/<slug>", methods=["DELETE"])
@require_auth(roles=["admin", "author"])
def delete_post(slug: str) -> tuple[Response, int]:
    """Delete a post and purge its search index entries."""
    with closing(get_db_connection(current_app.config["DB_PATH"])) as conn:
        existing = PostDAO.get_by_slug(conn, slug)
        if not existing:
            return jsonify({"status": "error", "message": "Post not found."}), 404

        if (
            g.current_user["role"] != "admin"
            and existing["author_id"] != g.current_user["id"]
        ):
            return (
                jsonify({"status": "error", "message": "Permission denied."}),
                403,
            )

        SearchEngine().remove_post_from_index(conn, existing["id"])
        PostDAO.delete(conn, existing["id"])

    return jsonify({"status": "success", "message": "Post deleted."}), 200


@post_bp.route("/<slug>/publish", methods=["POST"])
@require_auth(roles=["admin", "author"])
def publish_post(slug: str) -> tuple[Response, int]:
    """Transition a draft post to published and index it for search."""
    with closing(get_db_connection(current_app.config["DB_PATH"])) as conn:
        existing = PostDAO.get_by_slug(conn, slug)
        if not existing:
            return jsonify({"status": "error", "message": "Post not found."}), 404

        if (
            g.current_user["role"] != "admin"
            and existing["author_id"] != g.current_user["id"]
        ):
            return (
                jsonify({"status": "error", "message": "Permission denied."}),
                403,
            )

        published = PostDAO.publish(conn, existing["id"])
        TagDAO.recalculate_post_counts(conn)
        if published:
            _index_post_record(conn, published)

    return (
        jsonify(
            {"status": "success", "data": {"post": _format_post_response(published)}}
        ),
        200,
    )
