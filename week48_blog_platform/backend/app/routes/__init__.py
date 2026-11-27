"""HTTP Route blueprints package for PulsePress."""

from app.routes.analytics_routes import analytics_bp
from app.routes.auth_routes import auth_bp
from app.routes.comment_routes import comment_bp
from app.routes.health import health_bp
from app.routes.post_routes import post_bp
from app.routes.search_routes import search_bp
from app.routes.seo_routes import seo_bp
from app.routes.static_routes import static_bp
from app.routes.tag_routes import tag_bp

__all__ = [
    "health_bp",
    "static_bp",
    "seo_bp",
    "auth_bp",
    "post_bp",
    "search_bp",
    "tag_bp",
    "comment_bp",
    "analytics_bp",
]
