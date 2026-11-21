# PulseMesh: Production-Grade Microservices Architecture Platform

PulseMesh is an enterprise distributed microservices platform built from the ground up to demonstrate resilience, high concurrency, event-driven choreography, distributed transactions with compensating sagas, and real-time observability.

---

## 1. System Architecture

```text
+-----------------------------------------------------------------------------------------+
|                                PulseMesh System Architecture                            |
|                                                                                         |
|       [ External Clients / SPAs ]             [ Interactive Chaos Console ]             |
|                    |                                        |                           |
|                    v                                        v                           |
|        +-----------------------------------------------------------------------+        |
|        |                   PulseMesh API Gateway (Port 8000)                   |        |
|        |  * Dynamic Path Reverse Proxy       * Token Bucket Rate Limiter       |        |
|        |  * Aggregated Health Engine         * Correlation ID Tracer           |        |
|        |  * Static Console Asset Delivery    * Circuit Breaker & Load Balancer |        |
|        +-------------------+-----------------------------------+---------------+        |
|                            |                                   |                        |
|       +--------------------+                                   +-----------------+      |
|       |                                                                          |      |
|       v                                                                          v      |
|  +---------------------------+                         +------------------------------+ |
|  | Service Registry & Store  |                         |   CloudEvents Message Broker | |
|  | (Port 8001)               |                         |   * Thread-safe Pub/Sub      | |
|  | * In-Memory InstanceStore |                         |   * Dead-Letter Queue (DLQ)  | |
|  | * Heartbeat Watchdog      |                         |   * Replay & Quarantine      | |
|  +---------------------------+                         +------------------------------+ |
|       ^                                                                ^                |
|       | Heartbeats / Discovery                                         | Pub / Sub      |
|       +------------------------+-------------------+-------------------+                |
|                                |                   |                   |                |
|       v                        v                   v                   v                |
|  +----------------+   +----------------+   +----------------+   +--------------------+  |
|  |  User Service  |   | Catalog Service|   | Order Service  |   |Notification Service|  |
|  |  (Port 8002)   |   | (Port 8003)    |   | (Port 8004)    |   | (Port 8005)        |  |
|  |  users.db      |   | catalog.db     |   | orders.db      |   | notifications.db   |  |
|  |  (SQLite WAL)  |   | (SQLite WAL)   |   | (SQLite WAL)   |   | (SQLite WAL)       |  |
|  |                |   |                |   |                |   |                    |  |
|  | User profiles, |   | Products, SKU, |   | Distributed    |   | Event consumer,    |  |
|  | addresses, API |   | Atomic stock   |   | Saga Coord,    |   | Idempotent ledger, |  |
|  | keys & auth    |   | reservations   |   | Compensations  |   | Dispatch engine    |  |
|  +----------------+   +----------------+   +----------------+   +--------------------+  |
|    Replica: 8012        Replica: 8013        Replica: 8014                              |
+-----------------------------------------------------------------------------------------+
```

---

## 2. Core Platform Capabilities

### A. Dynamic Service Registry & Health Discovery (`services/registry/`)
- **Instance Store:** Thread-safe repository managing active nodes, health statuses (`HEALTHY`, `DEGRADED`, `DOWN`), weights, tags, and metadata.
- **Heartbeat & Lease Eviction:** Background daemon watchdog sweeping stale nodes exceeding configurable lease timeouts (default: 15s).
- **Graceful Lifecycle:** Automated node self-registration on boot and deregistration on shutdown via `ServiceRegistrar`.

### B. Resilient HTTP Client (`PulseClient`) & Fault Tolerance (`shared/`)
- **Circuit Breaker Pattern:** Martin Fowler 3-state state machine (`CLOSED`, `OPEN`, `HALF-OPEN`) preventing cascading cluster saturation with automatic cooldown resets.
- **Multi-Strategy Load Balancing:**
  - `ROUND_ROBIN`: Cyclic atomic round-robin across healthy nodes.
  - `LEAST_CONNECTIONS`: Dynamic routing to instances with fewest active requests.
  - `LATENCY_WEIGHTED`: Moving-average latency estimation routing to fastest replica.
  - `RANDOM`: Uniform random distribution.
- **Exponential Backoff Retries:** Automated retries with backoff factors for transient 5xx server errors and network glitches.

### C. Database-per-Service Isolation (`services/`)
- **User Service (Port 8002):** Isolated `users.db` handling user accounts, addresses, and API key authentication.
- **Catalog Service (Port 8003):** Isolated `catalog.db` with an **Atomic Stock Reservation Engine** (`/reserve`, `/release`, `/commit`) preventing overselling under race conditions.
- **Order Service (Port 8004):** Isolated `orders.db` executing multi-step checkouts via the **Orchestration Saga Coordinator** with automated compensating rollbacks (`COMPENSATE_STOCK_RELEASE`) on payment failure.
- **Notification Service (Port 8005):** Isolated `notifications.db` consuming `orders.events` with an idempotent deduplication ledger guaranteeing exactly-once semantics.

### D. CloudEvents Asynchronous Message Broker & DLQ (`shared/message_broker.py`)
- Conforms strictly to the CloudEvents v1.0 specification.
- Thread-safe pub/sub topics with bounded rolling event histories.
- Poison message quarantine via Dead-Letter Queue (DLQ) with one-click replaying and purge capabilities.

### E. API Gateway & Dynamic Ingress (`gateway/`)
- Central reverse proxy router dispatching `/api/v1/**` prefixes to internal port maps.
- Sliding-window token bucket rate limiter with burst capacity and CIDR/localhost whitelisting.
- Hop-by-hop header sanitization protecting backend microservices.
- Distributed `X-Correlation-ID` header injection across all request contexts.
- Aggregated cluster vitality probe (`GET /health`) reporting global status.

### F. Interactive Topology & Chaos Engineering Console (`frontend/`)
- Single-page command center served directly by the API Gateway at `/console`.
- Live vector SVG mesh graph with status-reactive node borders and animated pulse connectors.
- Real-time scale controls, traffic routing simulators, and chaos fault injection tools.
- Distributed saga trace waterfall viewer and Message Broker DLQ inspector.

---

## 3. Port Allocations & Topology

| Service | Port | Replica Port | Primary Database | Key Endpoints |
| :--- | :--- | :--- | :--- | :--- |
| **API Gateway** | 8000 | N/A | None (Stateless) | `/`, `/health`, `/console`, `/api/v1/**` |
| **Service Registry** | 8001 | N/A | In-Memory / WAL | `/api/v1/registry/services`, `/register`, `/heartbeat` |
| **User Service** | 8002 | 8012 | `users.db` | `/api/v1/users`, `/addresses`, `/authenticate` |
| **Catalog Service** | 8003 | 8013 | `catalog.db` | `/api/v1/products`, `/inventory/reserve`, `/release`, `/commit` |
| **Order Service** | 8004 | 8014 | `orders.db` | `/api/v1/orders`, `/saga-trace` |
| **Notification Service** | 8005 | N/A | `notifications.db` | `/api/v1/notifications`, `/processed-events` |

---

## 4. Concurrency Benchmark Performance Report

Simulated 500 requests across 50 concurrent worker threads through the API Gateway:

```text
======================================================================
  PULSEMESH CONCURRENCY BENCHMARK REPORT (DAY 7)
======================================================================
  * Total Requests        : 500
  * Successful Requests   : 500 (100.0%)
  * Failed Requests       : 0 (0.0%)
  * Concurrent Workers    : 50
  * Total Duration        : 0.35 seconds
  * Throughput            : 1411.63 req/sec
----------------------------------------------------------------------
  LATENCY PERCENTILES:
  * Min Latency           : 0.22 ms
  * Mean Latency          : 10.79 ms
  * Median (p50)          : 2.91 ms
  * 90th Percentile (p90) : 29.47 ms
  * 95th Percentile (p95) : 37.60 ms
  * 99th Percentile (p99) : 70.12 ms
  * Max Latency           : 84.50 ms
======================================================================
>> BENCHMARK PASSED: 100.0% SUCCESS UNDER CONCURRENT LOAD
======================================================================
```

---

## 5. Enterprise Quality Gates Summary

All 5 automated enterprise quality gates execute cleanly with zero warnings:

```text
======================================================================
  PULSEMESH MICROSERVICES: 5-STAGE AUTOMATED QUALITY GATES
======================================================================
  * FLAKE8 LINTER        : [OK] PASSED (0.90s)
  * BLACK FORMATTER      : [OK] PASSED (0.66s)
  * ISORT IMPORTS        : [OK] PASSED (0.29s)
  * BANDIT SECURITY      : [OK] PASSED (0.75s)
  * PYTEST COVERAGE      : [OK] PASSED (4.24s)
======================================================================
>> ALL QUALITY GATES PASSED! Safe to commit and deploy.
```

- Total Automated Tests: **109 passed** in 2.81s across 13 distinct test suites.
- Overall Project Coverage: **95.18% branch coverage** (exceeds the 90.0% project mandate).
- Zero-Emoji Compliance: 100% verified across all source code, tests, docs, and git commit messages.

---

## 6. Getting Started

### Prerequisites
- Python 3.10+
- Virtual environment (`venv`)

### Installation
```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
```

### Running the Test Suite
```bash
pytest -v
```

### Running the 5-Stage Quality Gates
```bash
python scripts/run_quality_checks.py
```

### Executing Concurrency Benchmarks
```bash
python scripts/run_benchmarks.py --requests 500 --concurrency 50
```

### Starting the Distributed Cluster
```bash
python scripts/start_mesh.py
```
Open your browser to `http://127.0.0.1:8000/console` to access the interactive microservices console and chaos engineering control plane.
