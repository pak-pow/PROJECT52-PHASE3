"""Automated service registration and background heartbeat client."""

import logging
import threading
from typing import Any, Optional

import requests

from shared.logging import setup_mesh_logger
from shared.models import HealthStatus, ServiceInstance


class ServiceRegistrar:
    """Manages service instance lifecycle with the Service Registry."""

    def __init__(
        self,
        service_name: str,
        port: int,
        host: str = "127.0.0.1",
        instance_id: Optional[str] = None,
        tags: Optional[list[str]] = None,
        weight: int = 1,
        metadata: Optional[dict[str, Any]] = None,
        registry_url: Optional[str] = None,
        instance_store: Optional[Any] = None,
        heartbeat_interval: float = 5.0,
        logger: Optional[logging.Logger] = None,
    ):
        self.service_name = service_name.strip().lower()
        self.port = port
        self.host = host
        self.instance_id = instance_id or f"{self.service_name}-{port}"
        self.tags = tags or []
        self.weight = weight
        self.metadata = metadata or {}
        self.registry_url = registry_url.rstrip("/") if registry_url else None
        self.instance_store = instance_store
        self.heartbeat_interval = heartbeat_interval
        self.logger = logger or setup_mesh_logger(
            f"{self.service_name}-registrar", self.instance_id
        )

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.registered_instance: Optional[ServiceInstance] = None

    def register(self) -> Optional[ServiceInstance]:
        """Register the service instance with the Service Registry."""
        # 1. In-process direct registration
        if self.instance_store is not None:
            inst = ServiceInstance(
                service_name=self.service_name,
                instance_id=self.instance_id,
                host=self.host,
                port=self.port,
                tags=self.tags,
                weight=self.weight,
                health_status=HealthStatus.HEALTHY,
                metadata=self.metadata,
            )
            self.registered_instance = self.instance_store.register(inst)
            self.logger.info(
                f"Registered instance '{self.instance_id}' directly in store"
            )
            return self.registered_instance

        # 2. Remote HTTP registration
        if self.registry_url is not None:
            payload = {
                "service_name": self.service_name,
                "instance_id": self.instance_id,
                "host": self.host,
                "port": self.port,
                "tags": self.tags,
                "weight": self.weight,
                "metadata": self.metadata,
            }
            try:
                url = f"{self.registry_url}/api/v1/registry/register"
                resp = requests.post(url, json=payload, timeout=5.0)
                if resp.status_code in (200, 201):
                    self.registered_instance = ServiceInstance.from_dict(resp.json())
                    self.logger.info(
                        f"Registered instance '{self.instance_id}' "
                        f"at {self.registry_url}"
                    )
                    return self.registered_instance
                else:
                    self.logger.error(
                        f"Registration failed: {resp.status_code} - {resp.text}"
                    )
            except Exception as exc:
                self.logger.error(f"Failed to connect to registry: {exc}")

        return None

    def heartbeat(self) -> bool:
        """Send a single heartbeat pulse to the registry."""
        if self.instance_store is not None:
            updated = self.instance_store.heartbeat(self.instance_id)
            return updated is not None

        if self.registry_url is not None:
            try:
                url = f"{self.registry_url}/api/v1/registry/heartbeat"
                resp = requests.post(
                    url, json={"instance_id": self.instance_id}, timeout=3.0
                )
                return resp.status_code == 200
            except Exception:
                return False

        return False

    def start_heartbeat(self) -> None:
        """Start background daemon thread periodically emitting heartbeats."""
        if self._thread is None or not self._thread.is_alive():
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run_heartbeat_loop,
                name=f"{self.instance_id}-hb",
                daemon=True,
            )
            self._thread.start()

    def stop_heartbeat(self, timeout: float = 2.0) -> None:
        """Signal the heartbeat thread to stop."""
        self._stop_event.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=timeout)

    def deregister(self) -> bool:
        """Stop heartbeats and deregister instance from the registry."""
        self.stop_heartbeat()

        if self.instance_store is not None:
            return self.instance_store.deregister(self.instance_id)

        if self.registry_url is not None:
            try:
                url = f"{self.registry_url}/api/v1/registry/deregister"
                resp = requests.delete(
                    url, json={"instance_id": self.instance_id}, timeout=3.0
                )
                return resp.status_code == 200
            except Exception:
                return False

        return False

    def _run_heartbeat_loop(self) -> None:
        """Internal periodic loop emitting heartbeats."""
        while not self._stop_event.is_set():
            if self._stop_event.wait(self.heartbeat_interval):
                break
            try:
                success = self.heartbeat()
                if not success:
                    # If heartbeat failed (e.g. lease expired), try re-registering
                    self.register()
            except Exception as e:
                self.logger.warning(f"Heartbeat loop exception: {e}")
