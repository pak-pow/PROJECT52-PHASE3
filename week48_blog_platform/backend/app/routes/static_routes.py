"""Static file serving blueprint for frontend workbench."""

from pathlib import Path

from flask import Blueprint, current_app, send_from_directory

from app.config.settings import Config

static_bp = Blueprint("static_routes", __name__)


def _get_frontend_dir() -> Path:
    """Retrieve resolved frontend root directory."""
    raw = current_app.config.get("FRONTEND_DIR")
    return Path(raw) if raw is not None else Config.FRONTEND_DIR


@static_bp.route("/", methods=["GET"])
def serve_index():
    """Serve public blog home single page application."""
    frontend_dir = _get_frontend_dir()
    return send_from_directory(str(frontend_dir / "public"), "index.html")


@static_bp.route("/src/<path:filename>", methods=["GET"])
def serve_src_assets(filename: str):
    """Serve modular JavaScript and CSS files from src directory."""
    frontend_dir = _get_frontend_dir()
    return send_from_directory(str(frontend_dir / "src"), filename)


@static_bp.route("/public/<path:filename>", methods=["GET"])
def serve_public_assets(filename: str):
    """Serve static public images and assets."""
    frontend_dir = _get_frontend_dir()
    return send_from_directory(str(frontend_dir / "public"), filename)
