"""Static asset delivery routes for the PulseSub mobile-first frontend."""

from pathlib import Path

from flask import Blueprint, abort, current_app, send_from_directory

from app.config.settings import Config

static_bp = Blueprint("static_routes", __name__)


def _get_frontend_dir() -> Path:
    return Path(current_app.config.get("FRONTEND_DIR", Config.FRONTEND_DIR))


@static_bp.route("/", methods=["GET"])
def index():
    """Serve the primary HTML document shell."""
    frontend_dir = _get_frontend_dir()
    public_dir = frontend_dir / "public"
    index_file = public_dir / "index.html"
    if not index_file.exists():
        abort(404)
    return send_from_directory(str(public_dir), "index.html")


@static_bp.route("/css/<path:filename>", methods=["GET"])
def serve_css(filename: str):
    """Serve modular stylesheet assets."""
    css_dir = _get_frontend_dir() / "src" / "css"
    return send_from_directory(str(css_dir), filename)


@static_bp.route("/js/<path:filename>", methods=["GET"])
def serve_js(filename: str):
    """Serve frontend JavaScript modules."""
    js_dir = _get_frontend_dir() / "src" / "js"
    return send_from_directory(str(js_dir), filename)


@static_bp.route("/public/<path:filename>", methods=["GET"])
def serve_public(filename: str):
    """Serve static public images, favicons, or manifests."""
    public_dir = _get_frontend_dir() / "public"
    return send_from_directory(str(public_dir), filename)
