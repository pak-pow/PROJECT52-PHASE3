"""Shared domain models, contracts, and context tracking for PulseMesh."""

import secrets
import threading
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Generator, Optional


class HealthStatus(str, Enum):
    """Enumeration of microservice node health states."""

    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    DOWN = "DOWN"
    UNKNOWN = "UNKNOWN"


def utc_now_iso() -> str:
    """Return the current UTC timestamp formatted as ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ServiceInstance:
    """Represents an active, registered microservice instance in the mesh."""

    service_name: str
    instance_id: str
    host: str
    port: int
    tags: list[str] = field(default_factory=list)
    weight: int = 1
    health_status: HealthStatus = HealthStatus.HEALTHY
    registered_at: str = field(default_factory=utc_now_iso)
    last_heartbeat: str = field(default_factory=utc_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def base_url(self) -> str:
        """Construct the HTTP base URL for this microservice instance."""
        return f"http://{self.host}:{self.port}"

    def update_heartbeat(self, status: Optional[HealthStatus] = None) -> None:
        """Update the last heartbeat timestamp to now (UTC)."""
        self.last_heartbeat = utc_now_iso()
        if status is not None:
            self.health_status = status

    def is_stale(self, lease_timeout_seconds: float) -> bool:
        """Check whether the instance lease has expired due to missing heartbeats."""
        try:
            hb_time = datetime.fromisoformat(self.last_heartbeat)
            if hb_time.tzinfo is None:
                hb_time = hb_time.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            diff = (now - hb_time).total_seconds()
            return diff > lease_timeout_seconds
        except (ValueError, TypeError):
            return True

    def to_dict(self) -> dict[str, Any]:
        """Serialize the instance record to a JSON-compatible dictionary."""
        data = asdict(self)
        data["health_status"] = self.health_status.value
        data["base_url"] = self.base_url
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ServiceInstance":
        """Deserialize a dictionary into a validated ServiceInstance."""
        status_val = data.get("health_status", HealthStatus.HEALTHY.value)
        try:
            status = HealthStatus(status_val)
        except ValueError:
            status = HealthStatus.UNKNOWN

        return cls(
            service_name=str(data["service_name"]),
            instance_id=str(data["instance_id"]),
            host=str(data.get("host", "127.0.0.1")),
            port=int(data["port"]),
            tags=list(data.get("tags", [])),
            weight=int(data.get("weight", 1)),
            health_status=status,
            registered_at=str(data.get("registered_at", utc_now_iso())),
            last_heartbeat=str(data.get("last_heartbeat", utc_now_iso())),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class ServiceRegistration:
    """Payload schema used when registering an instance with the Service Registry."""

    service_name: str
    host: str
    port: int
    instance_id: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    weight: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> Optional[str]:
        """Validate registration fields. Returns an error message or None if valid."""
        if not self.service_name or not self.service_name.strip():
            return "service_name cannot be empty"
        if not self.host or not self.host.strip():
            return "host cannot be empty"
        if not isinstance(self.port, int) or self.port < 1 or self.port > 65535:
            return "port must be an integer between 1 and 65535"
        if not isinstance(self.weight, int) or self.weight < 1:
            return "weight must be a positive integer"
        return None

    def to_instance(self) -> ServiceInstance:
        """Convert this validated registration into a live ServiceInstance."""
        inst_id = self.instance_id
        if not inst_id:
            inst_id = f"{self.service_name}-{self.port}-{secrets.token_hex(4)}"

        return ServiceInstance(
            service_name=self.service_name.strip().lower(),
            instance_id=inst_id,
            host=self.host.strip(),
            port=self.port,
            tags=self.tags,
            weight=self.weight,
            metadata=self.metadata,
        )


@dataclass
class CloudEvent:
    """Standardized event envelope conforming to CloudEvents v1.0 specification."""

    id: str
    source: str
    type: str
    data: dict[str, Any]
    specversion: str = "1.0"
    time: str = field(default_factory=utc_now_iso)
    datacontenttype: str = "application/json"
    correlation_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize CloudEvent to JSON-compatible dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CloudEvent":
        """Deserialize dictionary to CloudEvent."""
        return cls(
            id=str(data["id"]),
            source=str(data["source"]),
            type=str(data["type"]),
            data=dict(data.get("data", {})),
            specversion=str(data.get("specversion", "1.0")),
            time=str(data.get("time", utc_now_iso())),
            datacontenttype=str(data.get("datacontenttype", "application/json")),
            correlation_id=data.get("correlation_id"),
        )

    @classmethod
    def create(
        cls,
        source: str,
        event_type: str,
        data: dict[str, Any],
        correlation_id: Optional[str] = None,
    ) -> "CloudEvent":
        """Factory helper creating a fresh CloudEvent with a generated UUID."""
        event_id = f"evt_{secrets.token_hex(12)}"
        corr_id = correlation_id or CorrelationContext.get_correlation_id()
        return cls(
            id=event_id,
            source=source,
            type=event_type,
            data=data,
            correlation_id=corr_id,
        )


class CorrelationContext:
    """Thread-local context manager for distributed tracing correlation IDs."""

    _storage = threading.local()

    @classmethod
    def get_correlation_id(cls) -> str:
        """Retrieve current thread's correlation ID or generate a new one."""
        corr_id = getattr(cls._storage, "correlation_id", None)
        if not corr_id:
            corr_id = cls.generate_correlation_id()
            cls._storage.correlation_id = corr_id
        return corr_id

    @classmethod
    def set_correlation_id(cls, correlation_id: str) -> None:
        """Set correlation ID for the active execution thread."""
        cls._storage.correlation_id = correlation_id

    @classmethod
    def generate_correlation_id(cls) -> str:
        """Generate a random correlation identifier."""
        return f"corr_{secrets.token_hex(10)}"

    @classmethod
    def clear(cls) -> None:
        """Reset the thread-local correlation ID."""
        cls._storage.correlation_id = None

    @classmethod
    @contextmanager
    def scope(cls, correlation_id: Optional[str] = None) -> Generator[str, None, None]:
        """Context manager setting correlation ID temporarily within a block."""
        old_val = getattr(cls._storage, "correlation_id", None)
        active_id = correlation_id or cls.generate_correlation_id()
        cls._storage.correlation_id = active_id
        try:
            yield active_id
        finally:
            cls._storage.correlation_id = old_val
