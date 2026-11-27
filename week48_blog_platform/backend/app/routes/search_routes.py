"""Full-text BM25 search and autocomplete HTTP routes for PulsePress."""

from typing import List

from flask import Blueprint, Response, current_app, jsonify, request

from app.db.connection import get_db_connection
from app.services.search_engine import SearchEngine

search_bp = Blueprint("search", __name__, url_prefix="/api/search")


@search_bp.route("", methods=["GET"])
def search_posts() -> tuple[Response, int]:
    """Execute full-text BM25 search with optional tag slug filtering."""
    query = (request.args.get("q") or "").strip()
    raw_tags = (request.args.get("tags") or "").strip()
    tag_filters: List[str] = [
        t.strip().lower() for t in raw_tags.split(",") if t.strip()
    ]

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

    offset = (page - 1) * page_size
    engine = SearchEngine()

    with get_db_connection(current_app.config["DB_PATH"]) as conn:
        if tag_filters:
            raw = engine.search(conn, query=query, limit=200, offset=0)
            filtered = [
                item
                for item in raw["results"]
                if any(
                    t.get("slug", "").lower() in tag_filters
                    for t in item.get("tags", [])
                )
            ]
            total = len(filtered)
            results = filtered[offset : offset + page_size]
            terms = raw.get("terms", [])
        else:
            raw = engine.search(conn, query=query, limit=page_size, offset=offset)
            results = raw["results"]
            total = raw["total"]
            terms = raw.get("terms", [])

    return (
        jsonify(
            {
                "status": "success",
                "data": {
                    "query": query,
                    "terms": terms,
                    "results": results,
                    "total": total,
                    "page": page,
                    "page_size": page_size,
                },
            }
        ),
        200,
    )


@search_bp.route("/autocomplete", methods=["GET"])
def autocomplete() -> tuple[Response, int]:
    """Return prefix-matched indexed terms for search autocomplete."""
    prefix = (request.args.get("q") or "").strip()
    try:
        limit = min(20, max(1, int(request.args.get("limit", 8))))
    except ValueError:
        limit = 8

    with get_db_connection(current_app.config["DB_PATH"]) as conn:
        suggestions = SearchEngine().autocomplete(conn, prefix=prefix, limit=limit)

    return (
        jsonify(
            {
                "status": "success",
                "data": {"prefix": prefix, "suggestions": suggestions},
            }
        ),
        200,
    )
