"""Configuration profiles and environment definitions for PulseMesh."""

import os
from typing import Optional


class BaseMeshConfig:
    """Base configuration settings shared across all environments."""

    ENV_NAME: str = "base"
    DEBUG: bool = False
    TESTING: bool = False

    # Default Host & Ports Map
    DEFAULT_HOST: str = "127.0.0.1"
    PORT_GATEWAY: int = 8000
    PORT_REGISTRY: int = 8001
    PORT_USER_SERVICE: int = 8002
    PORT_CATALOG_SERVICE: int = 8003
    PORT_ORDER_SERVICE: int = 8004
    PORT_NOTIFICATION_SERVICE: int = 8005

    # Replica Ports for Multi-Instance Load Balancing & High Availability
    PORT_USER_REPLICA: int = 8012
    PORT_CATALOG_REPLICA: int = 8013
    PORT_ORDER_REPLICA: int = 8014

    # Service Registry & Discovery Timing (seconds)
    HEARTBEAT_INTERVAL: float = 5.0
    LEASE_TIMEOUT: float = 15.0
    EVICTION_SWEEP_INTERVAL: float = 5.0

    # Inter-Service Communication & Resilience Settings
    HTTP_REQUEST_TIMEOUT: float = 5.0
    CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = 5
    CIRCUIT_BREAKER_RECOVERY_TIMEOUT: float = 10.0
    CIRCUIT_BREAKER_HALF_OPEN_TRIALS: int = 2
    MAX_RETRIES: int = 3
    RETRY_BACKOFF_FACTOR: float = 0.2

    # Rate Limiter Settings
    RATE_LIMIT_RPS: int = 100
    RATE_LIMIT_BURST: int = 150

    @classmethod
    def get_service_url(cls, service_name: str, host: Optional[str] = None) -> str:
        """Resolve default service URL based on configuration port map."""
        target_host = host or cls.DEFAULT_HOST
        port_map = {
            "gateway": cls.PORT_GATEWAY,
            "registry": cls.PORT_REGISTRY,
            "user-service": cls.PORT_USER_SERVICE,
            "catalog-service": cls.PORT_CATALOG_SERVICE,
            "order-service": cls.PORT_ORDER_SERVICE,
            "notification-service": cls.PORT_NOTIFICATION_SERVICE,
        }
        port = port_map.get(service_name.lower(), 8000)
        return f"http://{target_host}:{port}"


class DevelopmentConfig(BaseMeshConfig):
    """Local development environment configuration."""

    ENV_NAME: str = "development"
    DEBUG: bool = True


class TestingConfig(BaseMeshConfig):
    """Automated testing environment configuration with fast timeouts."""

    ENV_NAME: str = "testing"
    TESTING: bool = True
    DEBUG: bool = False

    # Short timeouts for deterministic fast-running test suites
    HEARTBEAT_INTERVAL: float = 0.5
    LEASE_TIMEOUT: float = 1.0
    EVICTION_SWEEP_INTERVAL: float = 0.5
    HTTP_REQUEST_TIMEOUT: float = 1.0
    CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = 3
    CIRCUIT_BREAKER_RECOVERY_TIMEOUT: float = 1.0
    CIRCUIT_BREAKER_HALF_OPEN_TRIALS: int = 1


class ProductionConfig(BaseMeshConfig):
    """Production configuration profile."""

    ENV_NAME: str = "production"
    DEBUG: bool = False
    DEFAULT_HOST: str = "0.0.0.0"  # nosec B104


CONFIG_PROFILES: dict[str, type[BaseMeshConfig]] = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config(env_name: Optional[str] = None) -> type[BaseMeshConfig]:
    """Retrieve configuration class by environment name or default to development."""
    env = (env_name or os.environ.get("PULSEMESH_ENV", "development")).lower()
    return CONFIG_PROFILES.get(env, DevelopmentConfig)
