"""Dynamic reverse proxy and route dispatcher integrating PulseClient."""

import logging
import threading
import time
from typing import Any, Optional

from shared.circuit_breaker import CircuitBreakerOpenException
from shared.client import PulseClient, PulseResponse
from shared.logging import setup_mesh_logger
from shared.models import CorrelationContext

# Hop-by-hop headers that must not be forwarded by reverse proxy
HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "content-length",
    "host",
}


class ReverseProxyRouter:
    """Dynamic path-based route dispatcher forwarding calls to backend services."""

    DEFAULT_ROUTES: dict[str, str] = {
        "/api/v1/users": "user-service",
        "/api/v1/products": "catalog-service",
        "/api/v1/inventory": "catalog-service",
        "/api/v1/catalog": "catalog-service",
        "/api/v1/orders": "order-service",
        "/api/v1/notifications": "notification-service",
        "/api/v1/registry": "registry-service",
    }

    def __init__(
        self,
        pulse_client: Optional[PulseClient] = None,
        routes: Optional[dict[str, str]] = None,
        logger: Optional[logging.Logger] = None,
    ):
        self.pulse_client = pulse_client or PulseClient()
        self.routes = dict(routes or self.DEFAULT_ROUTES)
        self.logger = logger or setup_mesh_logger("gateway-proxy")
        self._lock = threading.RLock()
        self._stats: dict[str, dict[str, Any]] = {}

    def match_route(self, path: str) -> Optional[tuple[str, str]]:
        """Match incoming URL path to backend service name and target path.

        Returns:
            Tuple of (service_name, target_path) or None if unmatched.
        """
        clean_path = path.strip()
        if not clean_path.startswith("/"):
            clean_path = f"/{clean_path}"

        # Exact match or prefix match
        # Sort routes by length descending so most specific prefix matches first
        sorted_prefixes = sorted(self.routes.keys(), key=lambda p: len(p), reverse=True)

        for prefix in sorted_prefixes:
            if clean_path == prefix or clean_path.startswith(f"{prefix}/"):
                service_name = self.routes[prefix]
                return service_name, clean_path

        return None

    def register_route(self, prefix: str, service_name: str) -> None:
        """Dynamically add or override a prefix routing mapping."""
        with self._lock:
            clean_prefix = prefix.strip().rstrip("/")
            self.routes[clean_prefix] = service_name.strip().lower()
            self.logger.info(
                f"Registered route prefix '{clean_prefix}' -> '{service_name}'"
            )

    def forward_request(
        self,
        method: str,
        path: str,
        headers: Optional[dict[str, str]] = None,
        params: Optional[dict[str, Any]] = None,
        json_data: Optional[Any] = None,
        data: Optional[Any] = None,
        correlation_id: Optional[str] = None,
    ) -> tuple[int, dict[str, str], Any, dict[str, Any]]:
        """Forward HTTP request to destination microservice via PulseClient.

        Returns:
            Tuple of (status_code, response_headers, response_body, proxy_metadata)
        """
        matched = self.match_route(path)
        if not matched:
            err_body = {"error": f"No microservice route configured for path '{path}'"}
            return 404, {"Content-Type": "application/json"}, err_body, {}

        service_name, target_path = matched
        corr_id = correlation_id or CorrelationContext.get_correlation_id()

        # Sanitize incoming headers to strip hop-by-hop headers
        forward_headers = {}
        if headers:
            for k, v in headers.items():
                if k.lower() not in HOP_BY_HOP_HEADERS:
                    forward_headers[k] = v

        start_time = time.perf_counter()

        try:
            resp: PulseResponse = self.pulse_client.request(
                service_name=service_name,
                method=method,
                path=target_path,
                headers=forward_headers,
                params=params,
                json=json_data,
                data=data,
                correlation_id=corr_id,
            )

            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            self._record_telemetry(service_name, resp.status_code, latency_ms)

            # Strip hop-by-hop headers from upstream response
            clean_resp_headers = {
                k: v
                for k, v in resp.headers.items()
                if k.lower() not in HOP_BY_HOP_HEADERS
            }
            clean_resp_headers["X-Correlation-ID"] = corr_id
            clean_resp_headers["X-Upstream-Service"] = service_name
            clean_resp_headers["X-Upstream-Instance"] = resp.instance_id

            meta = {
                "service_name": service_name,
                "instance_id": resp.instance_id,
                "latency_ms": latency_ms,
                "status_code": resp.status_code,
            }

            return resp.status_code, clean_resp_headers, resp.data, meta

        except CircuitBreakerOpenException:
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            self._record_telemetry(service_name, 503, latency_ms)
            self.logger.warning(
                f"Circuit breaker OPEN for '{service_name}' on path '{path}'"
            )
            err_body = {
                "error": (
                    f"Circuit breaker is OPEN for service '{service_name}'. "
                    "Service is temporarily unavailable to prevent cascading failure."
                ),
                "service": service_name,
                "correlation_id": corr_id,
            }
            return (
                503,
                {
                    "Content-Type": "application/json",
                    "X-Correlation-ID": corr_id,
                },
                err_body,
                {"service_name": service_name, "error": "CircuitBreakerOpen"},
            )

        except Exception as exc:
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            self._record_telemetry(service_name, 503, latency_ms)
            self.logger.error(f"Proxy failure forwarding to '{service_name}': {exc}")
            err_body = {
                "error": f"Upstream service '{service_name}' unavailable: {str(exc)}",
                "service": service_name,
                "correlation_id": corr_id,
            }
            return (
                503,
                {
                    "Content-Type": "application/json",
                    "X-Correlation-ID": corr_id,
                },
                err_body,
                {"service_name": service_name, "error": str(exc)},
            )

    def _record_telemetry(
        self, service_name: str, status_code: int, latency_ms: float
    ) -> None:
        """Record route request counts, errors, and running latency stats."""
        with self._lock:
            svc_stats = self._stats.setdefault(
                service_name,
                {
                    "total_requests": 0,
                    "success_requests": 0,
                    "error_requests": 0,
                    "total_latency_ms": 0.0,
                    "avg_latency_ms": 0.0,
                },
            )
            svc_stats["total_requests"] += 1
            if status_code < 400:
                svc_stats["success_requests"] += 1
            else:
                svc_stats["error_requests"] += 1

            svc_stats["total_latency_ms"] += latency_ms
            svc_stats["avg_latency_ms"] = round(
                svc_stats["total_latency_ms"] / svc_stats["total_requests"], 2
            )

    def get_stats(self) -> dict[str, Any]:
        """Retrieve aggregated routing statistics across all microservices."""
        with self._lock:
            return {
                "routes": dict(self.routes),
                "services": {k: dict(v) for k, v in self._stats.items()},
            }
