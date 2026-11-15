"""Service Registry Flask application and heartbeat eviction watchdog."""

import logging
import threading
from typing import Optional

from flask import Flask, jsonify, request

from services.registry.instance_store import InstanceStore
from shared.config import BaseMeshConfig, get_config
from shared.logging import setup_mesh_logger
from shared.models import CorrelationContext, ServiceRegistration


class HeartbeatWatchdog:
    """Background watchdog thread that evicts stale service instances."""

    def __init__(
        self,
        instance_store: InstanceStore,
        lease_timeout: float,
        sweep_interval: float,
        logger: Optional[logging.Logger] = None,
    ):
        self.instance_store = instance_store
        self.lease_timeout = lease_timeout
        self.sweep_interval = sweep_interval
        self.logger = logger or setup_mesh_logger("registry-watchdog")
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Start the background eviction thread."""
        if self._thread is None or not self._thread.is_alive():
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run_loop,
                name="registry-watchdog",
                daemon=True,
            )
            self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        """Signal the background thread to stop and wait for it."""
        self._stop_event.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=timeout)

    def _run_loop(self) -> None:
        """Main periodic loop evicting expired instances."""
        while not self._stop_event.is_set():
            if self._stop_event.wait(self.sweep_interval):
                break
            try:
                evicted = self.instance_store.evict_stale(self.lease_timeout)
                if evicted:
                    self.logger.warning(
                        f"Evicted {len(evicted)} stale instances: {evicted}"
                    )
            except Exception as e:
                self.logger.error(f"Error in watchdog sweep: {e}")


def create_registry_app(
    config_class: Optional[type[BaseMeshConfig]] = None,
    start_watchdog: bool = False,
    instance_store: Optional[InstanceStore] = None,
) -> Flask:
    """Application factory for the PulseMesh Service Registry."""
    cfg = config_class or get_config()
    app = Flask(__name__)
    app.config.from_object(cfg)

    logger = setup_mesh_logger("registry", "registry-node-01")
    store = instance_store or InstanceStore()
    app.instance_store = store  # type: ignore[attr-defined]

    watchdog = None
    if start_watchdog:
        watchdog = HeartbeatWatchdog(
            instance_store=store,
            lease_timeout=cfg.LEASE_TIMEOUT,
            sweep_interval=cfg.EVICTION_SWEEP_INTERVAL,
            logger=logger,
        )
        watchdog.start()
        app.watchdog = watchdog  # type: ignore[attr-defined]

    @app.before_request
    def set_correlation() -> None:
        """Extract or generate correlation identifier for distributed tracing."""
        corr_id = request.headers.get("X-Correlation-ID")
        if not corr_id:
            corr_id = CorrelationContext.generate_correlation_id()
        CorrelationContext.set_correlation_id(corr_id)

    @app.after_request
    def attach_correlation(response):
        """Append correlation identifier to all outbound responses."""
        response.headers["X-Correlation-ID"] = CorrelationContext.get_correlation_id()
        return response

    @app.route("/health", methods=["GET"])
    def health_probe():
        """Vitality probe reporting registry status and active instance counts."""
        return (
            jsonify(
                {
                    "status": "UP",
                    "service": "registry",
                    "registered_instances": store.count(),
                }
            ),
            200,
        )

    @app.route("/api/v1/registry/register", methods=["POST"])
    def register_instance():
        """Register a new service instance or refresh an existing one."""
        payload = request.get_json(silent=True)
        if not payload or not isinstance(payload, dict):
            return (
                jsonify({"error": "invalid_payload", "message": "JSON body required"}),
                400,
            )

        reg = ServiceRegistration(
            service_name=payload.get("service_name", ""),
            host=payload.get("host", "127.0.0.1"),
            port=payload.get("port", 0),
            instance_id=payload.get("instance_id"),
            tags=payload.get("tags", []),
            weight=payload.get("weight", 1),
            metadata=payload.get("metadata", {}),
        )

        error = reg.validate()
        if error:
            return jsonify({"error": "validation_failed", "message": error}), 400

        instance = reg.to_instance()
        registered = store.register(instance)
        logger.info(
            f"Registered instance '{registered.instance_id}' "
            f"for service '{registered.service_name}'"
        )
        return jsonify(registered.to_dict()), 201

    @app.route("/api/v1/registry/heartbeat", methods=["POST"])
    def heartbeat():
        """Receive heartbeat pulse from an active service instance."""
        payload = request.get_json(silent=True) or {}
        instance_id = payload.get("instance_id") or request.args.get("instance_id")

        if not instance_id:
            return (
                jsonify(
                    {"error": "missing_parameter", "message": "instance_id is required"}
                ),
                400,
            )

        updated = store.heartbeat(str(instance_id).strip())
        if updated is None:
            return (
                jsonify(
                    {
                        "error": "instance_not_found",
                        "message": (
                            f"Instance '{instance_id}' is not registered "
                            "or lease expired"
                        ),
                    }
                ),
                404,
            )

        return jsonify(updated.to_dict()), 200

    @app.route("/api/v1/registry/deregister", methods=["DELETE", "POST"])
    def deregister():
        """Remove a service instance from the registry."""
        payload = request.get_json(silent=True) or {}
        instance_id = payload.get("instance_id") or request.args.get("instance_id")

        if not instance_id:
            return (
                jsonify(
                    {"error": "missing_parameter", "message": "instance_id is required"}
                ),
                400,
            )

        removed = store.deregister(str(instance_id).strip())
        if not removed:
            return (
                jsonify(
                    {
                        "error": "instance_not_found",
                        "message": f"Instance '{instance_id}' not found",
                    }
                ),
                404,
            )

        logger.info(f"Deregistered instance '{instance_id}'")
        return jsonify({"status": "deregistered", "instance_id": instance_id}), 200

    @app.route("/api/v1/registry/services", methods=["GET"])
    def list_services():
        """List all registered services, instance counts, and metadata."""
        return jsonify(store.get_services()), 200

    @app.route("/api/v1/registry/services/<service_name>", methods=["GET"])
    def get_service_instances(service_name: str):
        """Retrieve active instances for a given service."""
        healthy_param = request.args.get("healthy_only", "true").lower()
        healthy_only = healthy_param not in ("false", "0", "no")

        instances = store.get_instances(service_name, healthy_only=healthy_only)
        return (
            jsonify(
                {
                    "service_name": service_name,
                    "count": len(instances),
                    "healthy_only": healthy_only,
                    "instances": [inst.to_dict() for inst in instances],
                }
            ),
            200,
        )

    @app.route("/api/v1/registry/instances/<instance_id>", methods=["GET"])
    def get_single_instance(instance_id: str):
        """Retrieve details for a specific instance by ID."""
        inst = store.get_instance(instance_id)
        if inst is None:
            return (
                jsonify(
                    {
                        "error": "instance_not_found",
                        "message": f"Instance '{instance_id}' not found",
                    }
                ),
                404,
            )
        return jsonify(inst.to_dict()), 200

    return app
