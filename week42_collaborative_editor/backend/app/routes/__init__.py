"""Routes package init for PulsePad."""

from app.routes.document_routes import document_bp
from app.routes.health_routes import health_bp

__all__ = ["document_bp", "health_bp"]
