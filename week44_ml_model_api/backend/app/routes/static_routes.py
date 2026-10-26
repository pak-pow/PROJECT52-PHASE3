"""Static file and single-page application frontend routes."""

from pathlib import Path
from typing import Any

from flask import Blueprint, current_app, send_file, send_from_directory

from app.config.settings import Config

static_bp = Blueprint("static_routes", __name__)


@static_bp.route("/")
def index() -> Any:
    """Serve single-page frontend application entrypoint."""
    frontend_dir = Path(current_app.config.get("FRONTEND_DIR", Config.FRONTEND_DIR))
    index_file = frontend_dir / "public" / "index.html"
    if index_file.exists():
        return send_file(index_file)
    return "PulseInfer ML Model API is running.", 200


@static_bp.route("/src/<path:filename>")
def serve_src(filename: str) -> Any:
    """Serve JavaScript, CSS, and component assets from frontend/src."""
    frontend_dir = Path(current_app.config.get("FRONTEND_DIR", Config.FRONTEND_DIR))
    src_dir = frontend_dir / "src"
    return send_from_directory(src_dir, filename)


@static_bp.route("/public/<path:filename>")
def serve_public(filename: str) -> Any:
    """Serve public static assets from frontend/public."""
    frontend_dir = Path(current_app.config.get("FRONTEND_DIR", Config.FRONTEND_DIR))
    public_dir = frontend_dir / "public"
    return send_from_directory(public_dir, filename)
