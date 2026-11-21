"""PulseMesh Multi-Service Process Orchestrator and Cluster Starter.

Starts all core microservices and the API Gateway in managed threads
with signal handling and graceful shutdown.

Port Map:
- API Gateway: 8000
- Service Registry: 8001
- User Service (Primary): 8002
- Catalog Service (Primary): 8003
- Order Service (Primary): 8004
- Notification Service: 8005

Zero-emoji compliant.
"""

import signal
import sys
import threading
import time
from pathlib import Path
from typing import Any

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from werkzeug.serving import make_server

from gateway.app import create_gateway_app
from services.catalog.app import create_catalog_app
from services.notification.app import create_notification_app
from services.order.app import create_order_app
from services.registry.app import create_registry_app
from services.user.app import create_user_app
from shared.config import DevelopmentConfig
from shared.logging import setup_mesh_logger

logger = setup_mesh_logger("mesh-orchestrator")


class ServerThread(threading.Thread):
    """Thread wrapper managing a Werkzeug WSGI server instance."""

    def __init__(self, name: str, app: Any, host: str, port: int):
        super().__init__(daemon=True)
        self.service_name = name
        self.host = host
        self.port = port
        self.server = make_server(host, port, app)

    def run(self) -> None:
        """Run WSGI server listening loop."""
        logger.info(f"Starting {self.service_name} on http://{self.host}:{self.port}")
        self.server.serve_forever()

    def shutdown(self) -> None:
        """Gracefully stop WSGI server."""
        logger.info(f"Stopping {self.service_name}...")
        self.server.shutdown()


def start_cluster() -> None:
    """Launch full PulseMesh cluster."""
    cfg = DevelopmentConfig()
    servers: list[ServerThread] = []

    print("======================================================================")
    print("  PULSEMESH DISTRIBUTED SYSTEMS CLUSTER")
    print("======================================================================")
    print("  Launching microservices topology...")

    try:
        # 1. Service Registry (Port 8001)
        registry_app = create_registry_app(config_class=DevelopmentConfig)
        servers.append(
            ServerThread(
                "Service-Registry", registry_app, "127.0.0.1", cfg.PORT_REGISTRY
            )
        )

        # 2. User Service (Port 8002)
        user_app = create_user_app(config_class=DevelopmentConfig)
        servers.append(
            ServerThread("User-Service", user_app, "127.0.0.1", cfg.PORT_USER_SERVICE)
        )

        # 3. Catalog Service (Port 8003)
        catalog_app = create_catalog_app(config_class=DevelopmentConfig)
        servers.append(
            ServerThread(
                "Catalog-Service", catalog_app, "127.0.0.1", cfg.PORT_CATALOG_SERVICE
            )
        )

        # 4. Order Service (Port 8004)
        order_app = create_order_app(config_class=DevelopmentConfig)
        servers.append(
            ServerThread(
                "Order-Service", order_app, "127.0.0.1", cfg.PORT_ORDER_SERVICE
            )
        )

        # 5. Notification Service (Port 8005)
        notification_app = create_notification_app(config_class=DevelopmentConfig)
        servers.append(
            ServerThread(
                "Notification-Service",
                notification_app,
                "127.0.0.1",
                cfg.PORT_NOTIFICATION_SERVICE,
            )
        )

        # 6. API Gateway (Port 8000)
        gateway_app = create_gateway_app(config_class=DevelopmentConfig)
        servers.append(
            ServerThread("API-Gateway", gateway_app, "127.0.0.1", cfg.PORT_GATEWAY)
        )

        for server in servers:
            server.start()

        print("----------------------------------------------------------------------")
        print(f"  * API Gateway          : http://127.0.0.1:{cfg.PORT_GATEWAY}")
        print(f"  * Console Dashboard    : http://127.0.0.1:{cfg.PORT_GATEWAY}/console")
        print(f"  * Service Registry     : http://127.0.0.1:{cfg.PORT_REGISTRY}")
        print(f"  * User Service         : http://127.0.0.1:{cfg.PORT_USER_SERVICE}")
        print(f"  * Catalog Service      : http://127.0.0.1:{cfg.PORT_CATALOG_SERVICE}")
        print(f"  * Order Service        : http://127.0.0.1:{cfg.PORT_ORDER_SERVICE}")
        print(
            f"  * Notification Service : http://127.0.0.1:"
            f"{cfg.PORT_NOTIFICATION_SERVICE}"
        )
        print("======================================================================")
        print(">> CLUSTER READY: Press Ctrl+C to terminate.")

        def handle_signal(sig, frame):
            print("\nShutting down cluster...")
            for s in reversed(servers):
                s.shutdown()
            sys.exit(0)

        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)

        while True:
            time.sleep(1.0)

    except KeyboardInterrupt:
        print("\nTerminating cluster servers...")
        for s in reversed(servers):
            s.shutdown()


if __name__ == "__main__":
    start_cluster()
