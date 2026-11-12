"""Static asset and web application delivery routes for PulseAuth frontend."""

from pathlib import Path

from flask import (
    Blueprint,
    abort,
    current_app,
    render_template,
    request,
    send_from_directory,
)

from app.config.settings import Config

static_bp = Blueprint("static_routes", __name__)


def _get_frontend_dir() -> Path:
    """Retrieve absolute path to frontend directory."""
    return Path(current_app.config.get("FRONTEND_DIR", Config.FRONTEND_DIR))


@static_bp.route("/", methods=["GET"])
def index():
    """Serve the primary HTML application shell."""
    frontend_dir = _get_frontend_dir()
    public_dir = frontend_dir / "public"
    index_file = public_dir / "index.html"
    if not index_file.exists():
        abort(404)
    return send_from_directory(str(public_dir), "index.html")


@static_bp.route("/css/<path:filename>", methods=["GET"])
def serve_css(filename: str):
    """Serve stylesheet assets from src/css directory."""
    css_dir = _get_frontend_dir() / "src" / "css"
    if not (css_dir / filename).exists():
        abort(404)
    return send_from_directory(str(css_dir), filename)


@static_bp.route("/js/<path:filename>", methods=["GET"])
def serve_js(filename: str):
    """Serve frontend JavaScript modules from src/js directory."""
    js_dir = _get_frontend_dir() / "src" / "js"
    if not (js_dir / filename).exists():
        abort(404)
    return send_from_directory(str(js_dir), filename)


@static_bp.route("/public/<path:filename>", methods=["GET"])
def serve_public(filename: str):
    """Serve static public images, favicons, or manifest assets."""
    public_dir = _get_frontend_dir() / "public"
    if not (public_dir / filename).exists():
        abort(404)
    return send_from_directory(str(public_dir), filename)


@static_bp.route("/callback", methods=["GET"])
def oauth_callback():
    """Handle OAuth 2.0 authorization redirect callback in browser."""
    code = request.args.get("code", "")
    state = request.args.get("state", "")
    error = request.args.get("error", "")
    error_description = request.args.get("error_description", "")

    return render_template(
        "callback.html",
        code=code,
        state=state,
        error=error,
        error_description=error_description,
    )
