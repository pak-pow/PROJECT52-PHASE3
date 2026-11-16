"""Resilient inter-service HTTP client with discovery, LB and circuit breaking."""

import json as json_lib
import time
from dataclasses import dataclass
from typing import Any, Optional

import requests

from shared.circuit_breaker import (
    CircuitBreakerOpenException,
    CircuitBreakerRegistry,
)
from shared.config import BaseMeshConfig
from shared.load_balancer import LoadBalancer, LoadBalancerStrategy
from shared.models import CorrelationContext, HealthStatus, ServiceInstance


@dataclass
class PulseResponse:
    """Standardized response envelope returned by PulseClient."""

    status_code: int
    headers: dict[str, str]
    data: Any
    raw_text: str
    latency_ms: float
    instance_id: str
    service_name: str

    @property
    def is_success(self) -> bool:
        """True if status code is in 2xx or 3xx range."""
        return self.status_code < 400

    def json(self) -> Any:
        """Parse or return payload as JSON object."""
        if isinstance(self.data, (dict, list)):
            return self.data
        return json_lib.loads(self.raw_text)


class PulseClient:
    """Resilient inter-service client integrating discovery, LB, CB and retries."""

    def __init__(
        self,
        discovery_url: Optional[str] = None,
        instance_store: Optional[Any] = None,
        load_balancer: Optional[LoadBalancer] = None,
        circuit_breaker_registry: Optional[CircuitBreakerRegistry] = None,
        default_timeout: float = 5.0,
        max_retries: int = 3,
        retry_backoff_factor: float = 0.1,
        session: Optional[requests.Session] = None,
    ):
        self.discovery_url = discovery_url.rstrip("/") if discovery_url else None
        self.instance_store = instance_store
        self.circuit_breaker_registry = (
            circuit_breaker_registry or CircuitBreakerRegistry()
        )
        self.load_balancer = load_balancer or LoadBalancer(
            circuit_breaker_registry=self.circuit_breaker_registry
        )
        self.default_timeout = default_timeout
        self.max_retries = max_retries
        self.retry_backoff_factor = retry_backoff_factor
        self.session = session or requests.Session()

    def resolve_instances(self, service_name: str) -> list[ServiceInstance]:
        """Resolve available instances from local store, registry, or fallback."""
        target = service_name.strip().lower()

        # 1. Check local InstanceStore first
        if self.instance_store is not None:
            local_instances = self.instance_store.get_instances(
                target, healthy_only=False
            )
            if local_instances:
                return local_instances

        # 2. Check remote Discovery Registry URL
        if self.discovery_url is not None:
            try:
                url = (
                    f"{self.discovery_url}/api/v1/registry/services/{target}"
                    "?healthy_only=false"
                )
                res = self.session.get(url, timeout=self.default_timeout)
                if res.status_code == 200:
                    payload = res.json()
                    inst_list = payload.get("instances", [])
                    return [ServiceInstance.from_dict(item) for item in inst_list]
            except Exception:
                pass

        # 3. Fallback to default port mapping
        fallback_url = BaseMeshConfig.get_service_url(target)
        try:
            parts = fallback_url.replace("http://", "").split(":")
            host = parts[0]
            port = int(parts[1])
            return [
                ServiceInstance(
                    service_name=target,
                    instance_id=f"{target}-default",
                    host=host,
                    port=port,
                    health_status=HealthStatus.HEALTHY,
                )
            ]
        except Exception:
            return []

    def request(
        self,
        service_name: str,
        method: str,
        path: str,
        headers: Optional[dict[str, str]] = None,
        json: Optional[Any] = None,
        data: Optional[Any] = None,
        params: Optional[dict[str, Any]] = None,
        timeout: Optional[float] = None,
        strategy: Optional[LoadBalancerStrategy] = None,
    ) -> PulseResponse:
        """Execute resilient HTTP request with circuit breaking and retries."""
        service_key = service_name.strip().lower()
        cb = self.circuit_breaker_registry.get(service_key)

        # Check circuit breaker before doing work
        if not cb.can_execute():
            status = cb.get_status()
            raise CircuitBreakerOpenException(
                service_key, status["cooldown_remaining_seconds"]
            )

        req_timeout = timeout or self.default_timeout
        out_headers = dict(headers or {})
        corr_id = CorrelationContext.get_correlation_id()
        out_headers.setdefault("X-Correlation-ID", corr_id)

        last_exception: Optional[Exception] = None
        attempts = max(1, self.max_retries)

        for attempt in range(attempts):
            instances = self.resolve_instances(service_key)
            if not instances:
                raise RuntimeError(
                    f"No instances discovered for service '{service_key}'"
                )

            instance = self.load_balancer.choose(
                service_key, instances, strategy=strategy
            )
            if instance is None:
                raise RuntimeError(
                    f"No healthy instances available for service '{service_key}'"
                )

            url = f"{instance.base_url}/{path.lstrip('/')}"
            start_time = time.perf_counter()

            try:
                with self.load_balancer.track_connection(instance.instance_id):
                    resp = self.session.request(
                        method=method.upper(),
                        url=url,
                        headers=out_headers,
                        json=json,
                        data=data,
                        params=params,
                        timeout=req_timeout,
                    )

                latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
                self.load_balancer.record_latency(instance.instance_id, latency_ms)

                if resp.status_code >= 500:
                    # Server-side 5xx error -> transient failure, consider retrying
                    if attempt < attempts - 1:
                        backoff = self.retry_backoff_factor * (2**attempt)
                        time.sleep(backoff)
                        continue
                    else:
                        cb.record_failure()
                else:
                    cb.record_success()

                data_parsed: Any = None
                try:
                    data_parsed = resp.json()
                except Exception:
                    data_parsed = resp.text

                return PulseResponse(
                    status_code=resp.status_code,
                    headers=dict(resp.headers),
                    data=data_parsed,
                    raw_text=resp.text,
                    latency_ms=latency_ms,
                    instance_id=instance.instance_id,
                    service_name=service_key,
                )

            except (requests.RequestException, OSError) as exc:
                last_exception = exc
                latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
                self.load_balancer.record_latency(instance.instance_id, latency_ms)

                if attempt < attempts - 1:
                    backoff = self.retry_backoff_factor * (2**attempt)
                    time.sleep(backoff)
                    continue
                else:
                    cb.record_failure()
                    raise exc

        if last_exception:
            raise last_exception
        raise RuntimeError("Request execution completed without result")

    def get(self, service_name: str, path: str, **kwargs: Any) -> PulseResponse:
        """Convenience helper for HTTP GET requests."""
        return self.request(service_name, "GET", path, **kwargs)

    def post(self, service_name: str, path: str, **kwargs: Any) -> PulseResponse:
        """Convenience helper for HTTP POST requests."""
        return self.request(service_name, "POST", path, **kwargs)

    def put(self, service_name: str, path: str, **kwargs: Any) -> PulseResponse:
        """Convenience helper for HTTP PUT requests."""
        return self.request(service_name, "PUT", path, **kwargs)

    def delete(self, service_name: str, path: str, **kwargs: Any) -> PulseResponse:
        """Convenience helper for HTTP DELETE requests."""
        return self.request(service_name, "DELETE", path, **kwargs)
