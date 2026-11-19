"""Flask REST application for PulseMesh API Gateway and Reverse Proxy."""

from typing import Any, Optional

from flask import Flask, Response, jsonify, request

from gateway.proxy import ReverseProxyRouter
from gateway.rate_limiter import GatewayRateLimiter
from shared.client import PulseClient
from shared.config import BaseMeshConfig, get_config
from shared.logging import setup_mesh_logger
from shared.models import CorrelationContext, HealthStatus, utc_now_iso


def create_gateway_app(
    config_class: Optional[type[BaseMeshConfig]] = None,
    pulse_client: Optional[PulseClient] = None,
    rate_limiter: Optional[GatewayRateLimiter] = None,
    proxy_router: Optional[ReverseProxyRouter] = None,
    instance_store: Optional[Any] = None,
    instance_id: Optional[str] = None,
) -> Flask:
    """Application factory for API Gateway with reverse proxy and rate limiting."""
    cfg = config_class or get_config()
    app = Flask(__name__)
    app.config.from_object(cfg)

    inst_id = instance_id or f"gateway-{cfg.PORT_GATEWAY}"
    logger = setup_mesh_logger("api-gateway", inst_id)

    # Initialize client, rate limiter, router, and instance store
    client = pulse_client or PulseClient(instance_store=instance_store)
    limiter = rate_limiter or GatewayRateLimiter(
        rate_per_second=cfg.RATE_LIMIT_RPS,
        burst_capacity=cfg.RATE_LIMIT_BURST,
    )
    router = proxy_router or ReverseProxyRouter(pulse_client=client, logger=logger)

    app.pulse_client = client  # type: ignore[attr-defined]
    app.rate_limiter = limiter  # type: ignore[attr-defined]
    app.proxy_router = router  # type: ignore[attr-defined]
    app.instance_store = instance_store  # type: ignore[attr-defined]
    app.instance_id = inst_id  # type: ignore[attr-defined]

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
                    "timestamp": utc_now_iso(),
                }
            ),
            200,
        )

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
            # Standalone gateway initial state
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

    @app.route(
        "/api/v1/<path:subpath>", methods=["GET", "POST", "PUT", "DELETE", "PATCH"]
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
