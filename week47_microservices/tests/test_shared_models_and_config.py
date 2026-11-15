"""Unit tests for shared models, configuration, and logging."""

import json
import logging

from shared.config import (
    BaseMeshConfig,
    DevelopmentConfig,
    ProductionConfig,
    TestingConfig,
    get_config,
)
from shared.logging import StructuredJsonFormatter, setup_mesh_logger
from shared.models import (
    CloudEvent,
    CorrelationContext,
    HealthStatus,
    ServiceInstance,
    ServiceRegistration,
)


def test_service_instance_serialization() -> None:
    """Verify ServiceInstance serialization and deserialization."""
    inst = ServiceInstance(
        service_name="payment-service",
        instance_id="payment-01",
        host="10.0.0.5",
        port=8050,
        tags=["secure", "v2"],
        weight=3,
        health_status=HealthStatus.HEALTHY,
        metadata={"datacenter": "us-west"},
    )
    d = inst.to_dict()
    assert d["service_name"] == "payment-service"
    assert d["base_url"] == "http://10.0.0.5:8050"
    assert d["health_status"] == "HEALTHY"

    # Roundtrip from_dict
    restored = ServiceInstance.from_dict(d)
    assert restored.service_name == "payment-service"
    assert restored.instance_id == "payment-01"
    assert restored.host == "10.0.0.5"
    assert restored.port == 8050
    assert restored.weight == 3
    assert restored.health_status == HealthStatus.HEALTHY
    assert restored.metadata["datacenter"] == "us-west"


def test_service_instance_unknown_health_status() -> None:
    """Verify fallback to UNKNOWN for unrecognized status strings."""
    data = {
        "service_name": "test-service",
        "instance_id": "test-01",
        "port": 8080,
        "health_status": "FLAPPING_INVALID",
    }
    inst = ServiceInstance.from_dict(data)
    assert inst.health_status == HealthStatus.UNKNOWN


def test_service_instance_stale_detection() -> None:
    """Verify is_stale handles valid, expired, and malformed timestamps."""
    inst = ServiceInstance(
        service_name="test",
        instance_id="test-1",
        host="127.0.0.1",
        port=8000,
    )
    # Just created -> should not be stale with 10s lease
    assert not inst.is_stale(lease_timeout_seconds=10.0)

    # Backdated timestamp -> stale
    inst.last_heartbeat = "2020-01-01T00:00:00+00:00"
    assert inst.is_stale(lease_timeout_seconds=5.0)

    # Naive timestamp string
    inst.last_heartbeat = "2020-01-01T00:00:00"
    assert inst.is_stale(lease_timeout_seconds=5.0)

    # Test status update
    inst.update_heartbeat(status=HealthStatus.DEGRADED)
    assert inst.health_status == HealthStatus.DEGRADED

    # Test clearing store
    from services.registry.instance_store import InstanceStore

    store = InstanceStore()
    store.register(inst)
    assert store.count() == 1
    store.clear()
    assert store.count() == 0


def test_service_registration_validation() -> None:
    """Verify ServiceRegistration validation rules."""
    # Valid
    reg = ServiceRegistration(service_name="valid-svc", host="127.0.0.1", port=8000)
    assert reg.validate() is None
    inst = reg.to_instance()
    assert inst.service_name == "valid-svc"
    assert inst.instance_id is not None

    # Empty service_name
    reg_empty = ServiceRegistration(service_name="", host="127.0.0.1", port=8000)
    assert "service_name cannot be empty" in reg_empty.validate()

    # Empty host
    reg_nohost = ServiceRegistration(service_name="svc", host="  ", port=8000)
    assert "host cannot be empty" in reg_nohost.validate()

    # Invalid port range
    reg_badport = ServiceRegistration(service_name="svc", host="127.0.0.1", port=0)
    assert "port must be an integer" in reg_badport.validate()

    # Non-integer port
    reg_strport = ServiceRegistration(
        service_name="svc", host="127.0.0.1", port="eight"  # type: ignore
    )
    assert "port must be an integer" in reg_strport.validate()

    # Invalid weight
    reg_badweight = ServiceRegistration(
        service_name="svc", host="127.0.0.1", port=8000, weight=0
    )
    assert "weight must be a positive integer" in reg_badweight.validate()


def test_cloud_event_creation_and_serialization() -> None:
    """Verify CloudEvent factory and JSON serialization."""
    event = CloudEvent.create(
        source="/services/order-service",
        event_type="order.created",
        data={"order_id": "ord_123", "amount": 4999},
        correlation_id="corr_custom_999",
    )
    assert event.id.startswith("evt_")
    assert event.specversion == "1.0"
    assert event.source == "/services/order-service"
    assert event.type == "order.created"
    assert event.correlation_id == "corr_custom_999"

    d = event.to_dict()
    assert d["data"]["order_id"] == "ord_123"

    restored = CloudEvent.from_dict(d)
    assert restored.id == event.id
    assert restored.data["amount"] == 4999


def test_correlation_context_scope() -> None:
    """Verify CorrelationContext thread-local isolation and scope context manager."""
    CorrelationContext.clear()
    first_id = CorrelationContext.get_correlation_id()
    assert first_id.startswith("corr_")

    CorrelationContext.set_correlation_id("corr_explicit_1")
    assert CorrelationContext.get_correlation_id() == "corr_explicit_1"

    # Context manager scope override
    with CorrelationContext.scope("corr_scoped_2") as scoped_id:
        assert scoped_id == "corr_scoped_2"
        assert CorrelationContext.get_correlation_id() == "corr_scoped_2"

    # Restores after exit
    assert CorrelationContext.get_correlation_id() == "corr_explicit_1"

    CorrelationContext.clear()


def test_config_profiles_and_resolver() -> None:
    """Verify configuration resolution for dev, test, and prod."""
    dev_cfg = get_config("development")
    assert dev_cfg == DevelopmentConfig
    assert dev_cfg.DEBUG is True

    test_cfg = get_config("testing")
    assert test_cfg == TestingConfig
    assert test_cfg.TESTING is True
    assert test_cfg.LEASE_TIMEOUT < 5.0

    prod_cfg = get_config("production")
    assert prod_cfg == ProductionConfig
    assert prod_cfg.DEBUG is False

    # Default fallback
    fallback_cfg = get_config("unknown_environment")
    assert fallback_cfg == DevelopmentConfig

    # BaseMeshConfig service URL resolution
    url = BaseMeshConfig.get_service_url("order-service")
    assert url == "http://127.0.0.1:8004"
    url_custom = BaseMeshConfig.get_service_url("catalog-service", host="10.0.0.1")
    assert url_custom == "http://10.0.0.1:8003"


def test_structured_json_logger() -> None:
    """Verify StructuredJsonFormatter outputs valid JSON with correlation IDs."""
    formatter = StructuredJsonFormatter("user-service", "user-01")
    record = logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname=__file__,
        lineno=100,
        msg="User profile updated successfully",
        args=(),
        exc_info=None,
    )
    formatted = formatter.format(record)
    parsed = json.loads(formatted)

    assert parsed["service"] == "user-service"
    assert parsed["instance_id"] == "user-01"
    assert parsed["level"] == "INFO"
    assert parsed["message"] == "User profile updated successfully"
    assert "timestamp" in parsed
    assert "correlation_id" in parsed

    # Logger with exception and extra fields
    try:
        raise ValueError("Simulated connection timeout")
    except ValueError:
        import sys

        record_err = logging.LogRecord(
            name="test.logger",
            level=logging.ERROR,
            pathname=__file__,
            lineno=120,
            msg="Request failed",
            args=(),
            exc_info=sys.exc_info(),
        )
        record_err.extra_fields = {"retry_count": 3, "upstream": "catalog"}
        formatted_err = formatter.format(record_err)
        parsed_err = json.loads(formatted_err)
        assert "exception" in parsed_err
        assert parsed_err["extra"]["retry_count"] == 3

    # Logger factory test
    logger = setup_mesh_logger("test-svc", "inst-99")
    assert logger.name == "mesh.test-svc"
    assert len(logger.handlers) >= 1
