"""Routes package."""

from app.routes.health_routes import health_bp
from app.routes.task_routes import task_bp

__all__ = ["health_bp", "task_bp"]
