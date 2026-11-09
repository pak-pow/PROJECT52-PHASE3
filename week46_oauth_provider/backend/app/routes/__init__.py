"""Route blueprints package for PulseAuth."""

from app.routes.auth_routes import auth_bp
from app.routes.discovery_routes import discovery_bp
from app.routes.token_routes import token_bp
from app.routes.userinfo_routes import userinfo_bp

__all__ = ["discovery_bp", "auth_bp", "token_bp", "userinfo_bp"]
