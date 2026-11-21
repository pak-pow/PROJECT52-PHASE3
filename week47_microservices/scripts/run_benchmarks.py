"""PulseMesh 50-Worker Multi-Threaded Concurrency Benchmark Runner.

Simulates 500 requests across 50 concurrent worker threads through
the API Gateway, measuring throughput (req/s), error rates, and
latency percentiles (p50, p90, p95, p99).

Zero-emoji compliant.
"""

import argparse
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from gateway.app import create_gateway_app
from services.registry.instance_store import InstanceStore
from shared.client import PulseClient, PulseResponse
from shared.models import HealthStatus, ServiceInstance


def build_in_memory_mesh() -> Any:
    """Construct an in-memory mesh topology for benchmark execution."""
    store = InstanceStore()

    # Register mock instances in registry store
    store.register(
        ServiceInstance(
            service_name="user-service",
            instance_id="user-8002",
            host="127.0.0.1",
            port=8002,
            health_status=HealthStatus.HEALTHY,
        )
    )
    store.register(
        ServiceInstance(
            service_name="catalog-service",
            instance_id="catalog-8003",
            host="127.0.0.1",
            port=8003,
            health_status=HealthStatus.HEALTHY,
        )
    )

    # Mock resilient client that routes internally with microsecond timings
    def internal_request(service_name, method, path, **kwargs):
        t0 = time.perf_counter()
        # Simulate ~2-5ms internal microservice compute latency
        time.sleep(0.002)
        latency = (time.perf_counter() - t0) * 1000

        data: dict[str, Any] = {}
        if service_name == "catalog-service":
            data = {"products": [{"id": "prod_1", "name": "Standard Mesh Item"}]}
        elif service_name == "user-service":
            data = {"users": [{"id": "usr_1", "email": "dev@pulsemesh.io"}]}
        else:
            data = {"status": "OK"}

        return PulseResponse(
            status_code=200,
            headers={"Content-Type": "application/json"},
            data=data,
            raw_text="",
            latency_ms=latency,
            instance_id=f"{service_name}-node-1",
            service_name=service_name,
        )

    pulse = PulseClient(instance_store=store)
    # Monkey-patch internal request dispatcher for hermetic benchmarking
    pulse.request = internal_request  # type: ignore[assignment]

    app = create_gateway_app(instance_store=store, pulse_client=pulse)
    return app


def run_benchmark(
    total_requests: int = 500,
    concurrency: int = 50,
) -> dict[str, Any]:
    """Execute concurrent requests through API Gateway and return statistics."""
    app = build_in_memory_mesh()

    latencies_ms: list[float] = []
    successes = 0
    failures = 0

    endpoints = [
        "/api/v1/products",
        "/api/v1/users",
        "/api/v1/gateway/stats",
        "/health",
    ]

    def execute_worker_request(request_idx: int) -> tuple[int, float]:
        client = app.test_client()
        target_path = endpoints[request_idx % len(endpoints)]

        t_start = time.perf_counter()
        resp = client.get(
            target_path,
            headers={"X-Forwarded-For": f"10.0.0.{request_idx % 250 + 1}"},
        )
        duration_ms = (time.perf_counter() - t_start) * 1000
        return resp.status_code, duration_ms

    benchmark_start = time.perf_counter()

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [
            executor.submit(execute_worker_request, i) for i in range(total_requests)
        ]
        for f in as_completed(futures):
            try:
                status_code, dur = f.result()
                latencies_ms.append(dur)
                if status_code in (200, 201):
                    successes += 1
                else:
                    failures += 1
            except Exception:
                failures += 1

    total_duration_sec = time.perf_counter() - benchmark_start
    throughput = total_requests / total_duration_sec if total_duration_sec > 0 else 0

    sorted_latencies = sorted(latencies_ms)
    p50 = statistics.median(sorted_latencies) if sorted_latencies else 0.0
    p90 = (
        sorted_latencies[int(len(sorted_latencies) * 0.90)] if sorted_latencies else 0.0
    )
    p95 = (
        sorted_latencies[int(len(sorted_latencies) * 0.95)] if sorted_latencies else 0.0
    )
    p99 = (
        sorted_latencies[int(len(sorted_latencies) * 0.99)] if sorted_latencies else 0.0
    )
    mean_lat = statistics.mean(sorted_latencies) if sorted_latencies else 0.0
    min_lat = min(sorted_latencies) if sorted_latencies else 0.0
    max_lat = max(sorted_latencies) if sorted_latencies else 0.0

    return {
        "total_requests": total_requests,
        "concurrency": concurrency,
        "successes": successes,
        "failures": failures,
        "total_duration_sec": round(total_duration_sec, 2),
        "throughput_rps": round(throughput, 2),
        "mean_latency_ms": round(mean_lat, 2),
        "median_p50_ms": round(p50, 2),
        "p90_ms": round(p90, 2),
        "p95_ms": round(p95, 2),
        "p99_ms": round(p99, 2),
        "min_latency_ms": round(min_lat, 2),
        "max_latency_ms": round(max_lat, 2),
    }


def print_report(metrics: dict[str, Any]) -> None:
    """Print high-contrast structured ASCII benchmark report."""
    print("======================================================================")
    print("  PULSEMESH CONCURRENCY BENCHMARK REPORT (DAY 7)")
    print("======================================================================")
    print(f"  * Total Requests        : {metrics['total_requests']}")
    print(
        f"  * Successful Requests   : {metrics['successes']} "
        f"({round(metrics['successes']/metrics['total_requests']*100, 1)}%)"
    )
    print(
        f"  * Failed Requests       : {metrics['failures']} "
        f"({round(metrics['failures']/metrics['total_requests']*100, 1)}%)"
    )
    print(f"  * Concurrent Workers    : {metrics['concurrency']}")
    print(f"  * Total Duration        : {metrics['total_duration_sec']} seconds")
    print(f"  * Throughput            : {metrics['throughput_rps']} req/sec")
    print("----------------------------------------------------------------------")
    print("  LATENCY PERCENTILES:")
    print(f"  * Min Latency           : {metrics['min_latency_ms']} ms")
    print(f"  * Mean Latency          : {metrics['mean_latency_ms']} ms")
    print(f"  * Median (p50)          : {metrics['median_p50_ms']} ms")
    print(f"  * 90th Percentile (p90) : {metrics['p90_ms']} ms")
    print(f"  * 95th Percentile (p95) : {metrics['p95_ms']} ms")
    print(f"  * 99th Percentile (p99) : {metrics['p99_ms']} ms")
    print(f"  * Max Latency           : {metrics['max_latency_ms']} ms")
    print("======================================================================")
    if metrics["failures"] == 0:
        print(">> BENCHMARK PASSED: 100.0% SUCCESS UNDER CONCURRENT LOAD")
    else:
        print(">> BENCHMARK WARNING: DETECTED REQUEST FAILURES UNDER LOAD")
    print("======================================================================")


def main() -> int:
    """Entry point for CLI benchmark execution."""
    parser = argparse.ArgumentParser(
        description="PulseMesh Multi-Threaded Concurrency Benchmark Runner"
    )
    parser.add_argument(
        "--requests",
        "-n",
        type=int,
        default=500,
        help="Total number of requests (default: 500)",
    )
    parser.add_argument(
        "--concurrency",
        "-c",
        type=int,
        default=50,
        help="Concurrent worker threads (default: 50)",
    )
    args = parser.parse_args()

    results = run_benchmark(
        total_requests=args.requests,
        concurrency=args.concurrency,
    )
    print_report(results)
    return 0 if results["failures"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
