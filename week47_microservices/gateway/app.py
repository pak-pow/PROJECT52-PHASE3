"""Flask REST application for PulseMesh API Gateway and Reverse Proxy."""

import os
from typing import Any, Optional

from flask import Flask, Response, jsonify, request, send_from_directory

from gateway.proxy import ReverseProxyRouter
from gateway.rate_limiter import GatewayRateLimiter
from shared.client import PulseClient
from shared.config import BaseMeshConfig, get_config
from shared.load_balancer import LoadBalancerStrategy
from shared.logging import setup_mesh_logger
from shared.message_broker import MessageBroker, get_message_broker
from shared.models import CorrelationContext, HealthStatus, utc_now_iso


def create_gateway_app(
    config_class: Optional[type[BaseMeshConfig]] = None,
    pulse_client: Optional[PulseClient] = None,
    rate_limiter: Optional[GatewayRateLimiter] = None,
    proxy_router: Optional[ReverseProxyRouter] = None,
    instance_store: Optional[Any] = None,
    instance_id: Optional[str] = None,
    broker: Optional[MessageBroker] = None,
) -> Flask:
    """Application factory for API Gateway with reverse proxy and rate limiting."""
    cfg = config_class or get_config()
    # Resolve frontend directories for static UI serving
    frontend_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "frontend")
    )
    public_dir = os.path.join(frontend_dir, "public")
    src_dir = os.path.join(frontend_dir, "src")

    app = Flask(__name__, static_folder=src_dir, static_url_path="/static")
    app.config.from_object(cfg)

    inst_id = instance_id or f"gateway-{cfg.PORT_GATEWAY}"
    logger = setup_mesh_logger("api-gateway", inst_id)

    # Initialize client, rate limiter, router, instance store, and message broker
    client = pulse_client or PulseClient(instance_store=instance_store)
    limiter = rate_limiter or GatewayRateLimiter(
        rate_per_second=cfg.RATE_LIMIT_RPS,
        burst_capacity=cfg.RATE_LIMIT_BURST,
    )
    router = proxy_router or ReverseProxyRouter(pulse_client=client, logger=logger)
    msg_broker = broker or get_message_broker()

    app.pulse_client = client  # type: ignore[attr-defined]
    app.rate_limiter = limiter  # type: ignore[attr-defined]
    app.proxy_router = router  # type: ignore[attr-defined]
    app.instance_store = instance_store  # type: ignore[attr-defined]
    app.instance_id = inst_id  # type: ignore[attr-defined]
    app.broker = msg_broker  # type: ignore[attr-defined]

    @app.before_request
    def set_correlation() -> None:
        """Extract or generate distributed correlation identifier."""
        corr_id = request.headers.get("X-Correlation-ID")
        if not corr_id:
            corr_id = CorrelationContext.generate_correlation_id()
        CorrelationContext.set_correlation_id(corr_id)

    @app.after_request
    def attach_correlation(response):
        """Append correlation identifier to outbound response headers."""
        response.headers["X-Correlation-ID"] = CorrelationContext.get_correlation_id()
        response.headers["X-Gateway-Instance"] = inst_id
        return response

    @app.route("/", methods=["GET"])
    def gateway_root():
        """Root metadata endpoint describing API Gateway capabilities."""
        return (
            jsonify(
                {
                    "service": "api-gateway",
                    "status": "OPERATIONAL",
                    "instance_id": inst_id,
                    "routes": router.routes,
                    "console_url": "/console",
                    "timestamp": utc_now_iso(),
                }
            ),
            200,
        )

    @app.route("/console", methods=["GET"])
    def serve_console():
        """Serve the interactive Topology & Chaos Engineering Console HTML."""
        return send_from_directory(public_dir, "index.html")

    @app.route("/health", methods=["GET"])
    def aggregated_health():
        """Aggregated health probe across all registered microservices."""
        target_services = [
            "user-service",
            "catalog-service",
            "order-service",
            "notification-service",
            "registry-service",
        ]

        services_health: dict[str, dict[str, Any]] = {}
        healthy_count = 0

        store = getattr(app, "instance_store", None)

        for svc in target_services:
            instances = []
            if store is not None:
                instances = store.get_instances(svc, healthy_only=False)
            elif hasattr(client, "resolve_instances"):
                try:
                    instances = client.resolve_instances(svc)
                except Exception:
                    instances = []

            if not instances:
                services_health[svc] = {
                    "status": "UNKNOWN",
                    "total_instances": 0,
                    "healthy_instances": 0,
                    "message": "No instances registered",
                }
            else:
                healthy_insts = [
                    i
                    for i in instances
                    if getattr(i, "health_status", None) == HealthStatus.HEALTHY
                ]
                h_count = len(healthy_insts)
                t_count = len(instances)

                if h_count == t_count and h_count > 0:
                    svc_status = "HEALTHY"
                    healthy_count += 1
                elif h_count > 0:
                    svc_status = "DEGRADED"
                else:
                    svc_status = "DOWN"

                services_health[svc] = {
                    "status": svc_status,
                    "total_instances": t_count,
                    "healthy_instances": h_count,
                }

        # Calculate overall system status
        registered_services = [
            s for s, h in services_health.items() if h["total_instances"] > 0
        ]
        if not registered_services:
            overall_status = "HEALTHY"
            status_code = 200
        elif healthy_count == len(registered_services):
            overall_status = "HEALTHY"
            status_code = 200
        elif any(
            h["status"] in ("HEALTHY", "DEGRADED") for h in services_health.values()
        ):
            overall_status = "DEGRADED"
            status_code = 200
        else:
            overall_status = "DOWN"
            status_code = 503

        return (
            jsonify(
                {
                    "status": overall_status,
                    "service": "api-gateway",
                    "gateway_instance_id": inst_id,
                    "timestamp": utc_now_iso(),
                    "services": services_health,
                }
            ),
            status_code,
        )

    @app.route("/api/v1/gateway/stats", methods=["GET"])
    def gateway_stats():
        """Retrieve aggregated routing telemetry and rate limiting metrics."""
        cb_registry = getattr(client, "circuit_breaker_registry", None)
        cb_stats = cb_registry.get_all_statuses() if cb_registry else {}

        return (
            jsonify(
                {
                    "service": "api-gateway",
                    "instance_id": inst_id,
                    "rate_limiter": limiter.get_stats(),
                    "routing": router.get_stats(),
                    "circuit_breakers": cb_stats,
                    "timestamp": utc_now_iso(),
                }
            ),
            200,
        )

    # -----------------------------------------------------------------------
    # Chaos & Control Management Endpoints
    # -----------------------------------------------------------------------

    @app.route("/api/v1/chaos/circuit/trip", methods=["POST"])
    def chaos_trip_circuit():
        """Manually trip a service circuit breaker for chaos simulation."""
        data = request.get_json(silent=True) or {}
        service_name = data.get("service_name")
        if not service_name:
            return jsonify({"error": "service_name is required"}), 400

        cb_registry = getattr(client, "circuit_breaker_registry", None)
        if not cb_registry:
            return (
                jsonify({"error": "No circuit breaker registry configured"}),
                500,
            )

        cb = cb_registry.get(service_name)
        cb.trip()
        return (
            jsonify(
                {
                    "service_name": service_name,
                    "state": "OPEN",
                    "status": cb.get_status(),
                }
            ),
            200,
        )

    @app.route("/api/v1/chaos/circuit/reset", methods=["POST"])
    def chaos_reset_circuit():
        """Manually reset a circuit breaker back to healthy CLOSED state."""
        data = request.get_json(silent=True) or {}
        service_name = data.get("service_name")
        if not service_name:
            return jsonify({"error": "service_name is required"}), 400

        cb_registry = getattr(client, "circuit_breaker_registry", None)
        if not cb_registry:
            return (
                jsonify({"error": "No circuit breaker registry configured"}),
                500,
            )

        cb = cb_registry.get(service_name)
        cb.reset()
        return (
            jsonify(
                {
                    "service_name": service_name,
                    "state": "CLOSED",
                    "status": cb.get_status(),
                }
            ),
            200,
        )

    @app.route("/api/v1/chaos/instance/status", methods=["POST"])
    def chaos_update_instance_status():
        """Manually update an instance health status in the registry."""
        data = request.get_json(silent=True) or {}
        instance_id_arg = data.get("instance_id")
        status_str = data.get("health_status")
        if not instance_id_arg or not status_str:
            return (
                jsonify({"error": "instance_id and health_status are required"}),
                400,
            )

        store = getattr(app, "instance_store", None)
        if not store:
            return jsonify({"error": "No instance store configured"}), 500

        inst = store.get_instance(instance_id_arg)
        if not inst:
            return (
                jsonify({"error": f"Instance '{instance_id_arg}' not found"}),
                404,
            )

        try:
            inst.health_status = HealthStatus(status_str.upper())
            return (
                jsonify(
                    {
                        "instance_id": instance_id_arg,
                        "health_status": inst.health_status.value,
                    }
                ),
                200,
            )
        except ValueError:
            return (
                jsonify({"error": f"Invalid health status '{status_str}'"}),
                400,
            )

    @app.route("/api/v1/gateway/load-balancer/strategy", methods=["POST"])
    def set_load_balancer_strategy():
        """Configure the default load balancing algorithm at runtime."""
        data = request.get_json(silent=True) or {}
        strat_str = data.get("strategy")
        if not strat_str:
            return jsonify({"error": "strategy is required"}), 400

        try:
            strat = LoadBalancerStrategy[strat_str.strip().upper()]
            if hasattr(client, "load_balancer"):
                client.load_balancer.default_strategy = strat
                return (
                    jsonify({"strategy": strat.value, "status": "UPDATED"}),
                    200,
                )
            return (
                jsonify({"error": "No load balancer configured on client"}),
                500,
            )
        except KeyError:
            return (
                jsonify({"error": f"Unknown strategy algorithm '{strat_str}'"}),
                400,
            )

    # -----------------------------------------------------------------------
    # Message Broker & DLQ Management Endpoints
    # -----------------------------------------------------------------------

    @app.route("/api/v1/broker/events", methods=["GET"])
    def get_broker_events():
        """Retrieve recent events published to the message broker."""
        topic = request.args.get("topic", "orders.events")
        limit = request.args.get("limit", 50, type=int)
        broker_obj = getattr(app, "broker", None) or get_message_broker()
        events = broker_obj.get_topic_history(topic, limit=limit)
        return jsonify({"topic": topic, "events": events, "count": len(events)}), 200

    @app.route("/api/v1/broker/dlq", methods=["GET"])
    def get_broker_dlq():
        """Retrieve poisoned messages quarantined in the Dead-Letter Queue."""
        broker_obj = getattr(app, "broker", None) or get_message_broker()
        dlq_items = broker_obj.get_dlq()
        return jsonify({"dlq": dlq_items, "count": len(dlq_items)}), 200

    @app.route("/api/v1/broker/dlq/<dlq_id>/replay", methods=["POST"])
    def replay_broker_dlq(dlq_id: str):
        """Replay a quarantined Dead-Letter Queue message to its consumer."""
        broker_obj = getattr(app, "broker", None) or get_message_broker()
        replayed = broker_obj.replay_dlq(dlq_id)
        status_code = 200 if replayed else 400
        return (
            jsonify({"dlq_id": dlq_id, "replayed": replayed}),
            status_code,
        )

    @app.route("/api/v1/broker/dlq", methods=["DELETE"])
    def clear_broker_dlq():
        """Purge all quarantined records from the Dead-Letter Queue."""
        broker_obj = getattr(app, "broker", None) or get_message_broker()
        broker_obj.clear_dlq()
        return jsonify({"status": "CLEARED"}), 200

    # -----------------------------------------------------------------------
    # Dynamic Reverse Proxy Catch-All Dispatcher
    # -----------------------------------------------------------------------

    @app.route(
        "/api/v1/<path:subpath>",
        methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    )
    def reverse_proxy_dispatch(subpath: str):
        """Dynamic reverse proxy dispatch with rate limiting and correlation."""
        full_path = f"/api/v1/{subpath}"
        corr_id = CorrelationContext.get_correlation_id()

        # 1. Rate Limiting Check
        forwarded_for = request.headers.get("X-Forwarded-For", "")
        client_key = (
            forwarded_for.split(",")[0].strip()
            if forwarded_for
            else (request.remote_addr or "127.0.0.1")
        )

        limiter_check = limiter.check_rate_limit(client_key)
        if not limiter_check["allowed"]:
            err_resp = jsonify(
                {
                    "error": "Rate limit exceeded. Too many requests.",
                    "retry_after": limiter_check["retry_after"],
                    "correlation_id": corr_id,
                }
            )
            err_resp.status_code = 429
            err_resp.headers["Retry-After"] = str(limiter_check["retry_after"])
            err_resp.headers["X-RateLimit-Limit"] = str(limiter_check["limit"])
            err_resp.headers["X-RateLimit-Remaining"] = "0"
            err_resp.headers["X-Correlation-ID"] = corr_id
            return err_resp

        # 2. Extract request body and parameters
        json_body = request.get_json(silent=True)
        raw_body = None if json_body is not None else request.get_data()
        params = request.args.to_dict()
        inbound_headers = dict(request.headers)

        # 3. Forward request through reverse proxy
        status_code, out_headers, out_data, _ = router.forward_request(
            method=request.method,
            path=full_path,
            headers=inbound_headers,
            params=params,
            json_data=json_body,
            data=raw_body,
            correlation_id=corr_id,
        )

        # 4. Construct outbound Flask response
        if isinstance(out_data, (dict, list)):
            resp = jsonify(out_data)
        else:
            resp = Response(
                out_data or "",
                mimetype=out_headers.get("Content-Type", "application/json"),
            )

        resp.status_code = status_code

        # Attach response headers
        for h_key, h_val in out_headers.items():
            if h_key.lower() not in ("content-length", "content-type"):
                resp.headers[h_key] = h_val

        resp.headers["X-RateLimit-Limit"] = str(limiter_check["limit"])
        resp.headers["X-RateLimit-Remaining"] = str(limiter_check["remaining"])
        resp.headers["X-Correlation-ID"] = corr_id

        return resp

    return app
