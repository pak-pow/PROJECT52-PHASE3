"""HTTP Route blueprints package for PulsePress."""

from app.routes.health import health_bp
from app.routes.seo_routes import seo_bp
from app.routes.static_routes import static_bp

__all__ = ["health_bp", "static_bp", "seo_bp"]
