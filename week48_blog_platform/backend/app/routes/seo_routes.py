"""SEO routes for sitemap.xml, feeds, robots.txt, and metadata endpoints."""

from typing import Any, Dict

from flask import Blueprint, Response, current_app, jsonify

from app.db.connection import get_db_connection
from app.models.post import PostDAO
from app.models.tag import TagDAO
from app.seo import RobotsGenerator, RSSFeedGenerator, SEOEngine, SitemapGenerator

seo_bp = Blueprint("seo", __name__)


def _get_seo_engine() -> SEOEngine:
    base_url = current_app.config.get("SITE_URL", "http://localhost:5000")
    site_name = current_app.config.get("SITE_NAME", "PulsePress")
    desc = current_app.config.get(
        "SITE_DESCRIPTION",
        "A full-featured technical blog with advanced SEO and full-text search.",
    )
    return SEOEngine(base_url=base_url, site_name=site_name, default_description=desc)


@seo_bp.route("/sitemap.xml", methods=["GET"])
def sitemap_xml() -> Response:
    """Return XML Sitemap conforming to Sitemaps 0.9 protocol."""
    base_url = current_app.config.get("SITE_URL", "http://localhost:5000")
    generator = SitemapGenerator(base_url=base_url)

    with get_db_connection(current_app.config["DB_PATH"]) as conn:
        posts, _ = PostDAO.list_posts(conn, status="published", page_size=1000)
        tags = TagDAO.list_all(conn)

    xml_content = generator.generate(posts=posts, tags=tags)
    return Response(xml_content, mimetype="application/xml")


@seo_bp.route("/rss.xml", methods=["GET"])
@seo_bp.route("/feed.xml", methods=["GET"])
def rss_xml() -> Response:
    """Return RSS 2.0 syndication feed."""
    base_url = current_app.config.get("SITE_URL", "http://localhost:5000")
    site_name = current_app.config.get("SITE_NAME", "PulsePress")
    desc = current_app.config.get(
        "SITE_DESCRIPTION",
        "A full-featured technical blog with advanced SEO and full-text search.",
    )
    generator = RSSFeedGenerator(
        base_url=base_url,
        site_name=site_name,
        site_description=desc,
    )

    with get_db_connection(current_app.config["DB_PATH"]) as conn:
        posts, _ = PostDAO.list_posts(conn, status="published", page_size=50)

    xml_content = generator.generate_rss(posts=posts)
    return Response(xml_content, mimetype="application/rss+xml")


@seo_bp.route("/atom.xml", methods=["GET"])
def atom_xml() -> Response:
    """Return Atom 1.0 syndication feed."""
    base_url = current_app.config.get("SITE_URL", "http://localhost:5000")
    site_name = current_app.config.get("SITE_NAME", "PulsePress")
    desc = current_app.config.get(
        "SITE_DESCRIPTION",
        "A full-featured technical blog with advanced SEO and full-text search.",
    )
    generator = RSSFeedGenerator(
        base_url=base_url,
        site_name=site_name,
        site_description=desc,
    )

    with get_db_connection(current_app.config["DB_PATH"]) as conn:
        posts, _ = PostDAO.list_posts(conn, status="published", page_size=50)

    xml_content = generator.generate_atom(posts=posts)
    return Response(xml_content, mimetype="application/atom+xml")


@seo_bp.route("/robots.txt", methods=["GET"])
def robots_txt() -> Response:
    """Return robots.txt crawl directives."""
    base_url = current_app.config.get("SITE_URL", "http://localhost:5000")
    generator = RobotsGenerator(base_url=base_url)
    txt_content = generator.generate()
    return Response(txt_content, mimetype="text/plain")


@seo_bp.route("/api/seo/site", methods=["GET"])
def api_seo_site() -> Response:
    """Return site-wide SEO metadata and JSON-LD structured data."""
    seo = _get_seo_engine()
    meta = seo.generate_meta_tags()
    json_ld = seo.generate_json_ld()
    html_head = seo.render_html_meta()

    data: Dict[str, Any] = {
        "status": "success",
        "data": {
            "meta_tags": meta,
            "json_ld": json_ld,
            "html_head": html_head,
        },
    }
    return jsonify(data)


@seo_bp.route("/api/seo/post/<identifier>", methods=["GET"])
def api_seo_post(identifier: str) -> Response:
    """Return post SEO metadata by numeric ID or slug."""
    with get_db_connection(current_app.config["DB_PATH"]) as conn:
        post = None
        if identifier.isdigit():
            post = PostDAO.get_by_id(conn, int(identifier))
        if not post:
            post = PostDAO.get_by_slug(conn, identifier)

    if not post:
        return jsonify({"status": "error", "message": "Post not found"}), 404

    seo = _get_seo_engine()
    meta = seo.generate_meta_tags(post=post)
    json_ld = seo.generate_json_ld(post=post)
    html_head = seo.render_html_meta(post=post)

    data: Dict[str, Any] = {
        "status": "success",
        "data": {
            "post_id": post["id"],
            "slug": post["slug"],
            "meta_tags": meta,
            "json_ld": json_ld,
            "html_head": html_head,
        },
    }
    return jsonify(data)
