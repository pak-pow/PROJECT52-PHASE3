"""Structured JSON logging with automated correlation ID tracking for PulseMesh."""

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Optional

from shared.models import CorrelationContext


class StructuredJsonFormatter(logging.Formatter):
    """Custom logging formatter outputting standard JSON objects."""

    def __init__(self, service_name: str, instance_id: Optional[str] = None):
        super().__init__()
        self.service_name = service_name
        self.instance_id = instance_id or "default"

    def format(self, record: logging.LogRecord) -> str:
        """Format log record into a single-line JSON string."""
        log_payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "service": self.service_name,
            "instance_id": self.instance_id,
            "correlation_id": CorrelationContext.get_correlation_id(),
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Attach exception info if present
        if record.exc_info:
            log_payload["exception"] = self.formatException(record.exc_info)

        # Attach custom extra fields if provided
        if hasattr(record, "extra_fields") and isinstance(record.extra_fields, dict):
            log_payload["extra"] = record.extra_fields

        return json.dumps(log_payload, ensure_ascii=False)


def setup_mesh_logger(
    service_name: str,
    instance_id: Optional[str] = None,
    level: int = logging.INFO,
) -> logging.Logger:
    """Configure and return a structured JSON logger for a microservice."""
    logger_name = f"mesh.{service_name}"
    logger = logging.getLogger(logger_name)
    logger.setLevel(level)

    # Avoid duplicate handlers if logger was already created
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(StructuredJsonFormatter(service_name, instance_id))
        logger.addHandler(handler)
        logger.propagate = False

    return logger
