"""Route blueprints package for PulseAuth."""

from app.routes.auth_routes import auth_bp
from app.routes.client_routes import client_bp
from app.routes.discovery_routes import discovery_bp
from app.routes.introspection_routes import introspection_bp
from app.routes.resource_routes import resource_bp
from app.routes.revocation_routes import revocation_bp
from app.routes.token_routes import token_bp
from app.routes.user_auth_routes import user_auth_bp
from app.routes.userinfo_routes import userinfo_bp

__all__ = [
    "discovery_bp",
    "auth_bp",
    "token_bp",
    "userinfo_bp",
    "revocation_bp",
    "introspection_bp",
    "resource_bp",
    "client_bp",
    "user_auth_bp",
]
