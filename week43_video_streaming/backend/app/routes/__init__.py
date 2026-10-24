"""Routes package for PulseStream."""

from app.routes.health import health_bp
from app.routes.job_routes import job_bp
from app.routes.video_routes import video_bp

__all__ = ["health_bp", "job_bp", "video_bp"]
