"""Route blueprints package for PulseAuth."""

from app.routes.auth_routes import auth_bp
from app.routes.discovery_routes import discovery_bp

__all__ = ["discovery_bp", "auth_bp"]
