"""Thread-safe instance store for the Service Registry."""

import threading
from typing import Any, Optional

from shared.models import HealthStatus, ServiceInstance


class InstanceStore:
    """In-memory repository of registered microservice instances."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._instances: dict[str, ServiceInstance] = {}

    def register(
        self,
        instance: ServiceInstance,
        touch_heartbeat: bool = True,
    ) -> ServiceInstance:
        """Register or refresh a microservice instance."""
        with self._lock:
            if touch_heartbeat:
                instance.update_heartbeat()
            self._instances[instance.instance_id] = instance
            return instance

    def heartbeat(self, instance_id: str) -> Optional[ServiceInstance]:
        """Update last heartbeat timestamp for an existing instance."""
        with self._lock:
            instance = self._instances.get(instance_id)
            if instance is not None:
                instance.update_heartbeat()
                return instance
            return None

    def deregister(self, instance_id: str) -> bool:
        """Remove an instance from the registry upon graceful shutdown."""
        with self._lock:
            if instance_id in self._instances:
                del self._instances[instance_id]
                return True
            return False

    def get_instance(self, instance_id: str) -> Optional[ServiceInstance]:
        """Retrieve a single instance by its unique identifier."""
        with self._lock:
            return self._instances.get(instance_id)

    def get_instances(
        self,
        service_name: str,
        healthy_only: bool = True,
    ) -> list[ServiceInstance]:
        """Retrieve all instances for a specific service."""
        with self._lock:
            target_name = service_name.strip().lower()
            results = []
            for inst in self._instances.values():
                if inst.service_name.lower() == target_name:
                    if not healthy_only or inst.health_status == HealthStatus.HEALTHY:
                        results.append(inst)
            return results

    def get_services(self) -> dict[str, dict[str, Any]]:
        """Return an aggregated overview of all services and their instances."""
        with self._lock:
            services_map: dict[str, dict[str, Any]] = {}
            for inst in self._instances.values():
                s_name = inst.service_name
                if s_name not in services_map:
                    services_map[s_name] = {
                        "service_name": s_name,
                        "total_instances": 0,
                        "healthy_instances": 0,
                        "instances": [],
                    }
                services_map[s_name]["total_instances"] += 1
                if inst.health_status == HealthStatus.HEALTHY:
                    services_map[s_name]["healthy_instances"] += 1
                services_map[s_name]["instances"].append(inst.to_dict())

            return services_map

    def evict_stale(self, lease_timeout_seconds: float) -> list[str]:
        """Evict instances whose heartbeat lease has expired."""
        with self._lock:
            stale_ids = []
            for inst_id, inst in list(self._instances.items()):
                if inst.is_stale(lease_timeout_seconds):
                    stale_ids.append(inst_id)
                    del self._instances[inst_id]
            return stale_ids

    def count(self) -> int:
        """Return the current count of registered instances."""
        with self._lock:
            return len(self._instances)

    def clear(self) -> None:
        """Remove all registered instances."""
        with self._lock:
            self._instances.clear()
