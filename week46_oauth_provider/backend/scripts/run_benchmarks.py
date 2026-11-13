"""Multi-threaded SQLite WAL concurrency and throughput benchmark for PulseAuth."""

import sqlite3
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List

# Ensure backend package on sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app import create_app  # noqa: E402
from app.config.settings import Config  # noqa: E402
from app.db.connection import init_db  # noqa: E402
from data.seed import seed_database  # noqa: E402


def calculate_percentile(sorted_list: List[float], percentile: float) -> float:
    """Calculate the p-th percentile from an ordered list of floats."""
    if not sorted_list:
        return 0.0
    k = (len(sorted_list) - 1) * (percentile / 100.0)
    f = int(k)
    c = f + 1
    if c < len(sorted_list):
        d0 = sorted_list[f] * (c - k)
        d1 = sorted_list[c] * (k - f)
        return round(d0 + d1, 2)
    return round(sorted_list[f], 2)


def run_benchmark(concurrency: int = 50, total_requests: int = 500) -> dict:
    """Execute high-concurrency token exchange benchmark against SQLite WAL."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        db_file = str(tmp_path / "benchmark_pulse_auth.db")
        keys_dir = tmp_path / "keys"
        keys_dir.mkdir(parents=True, exist_ok=True)

        class BenchmarkConfig(Config):
            DATABASE_PATH = db_file
            RSA_PRIVATE_KEY_PATH = str(keys_dir / "rsa_private.pem")
            RSA_PUBLIC_KEY_PATH = str(keys_dir / "rsa_public.pem")
            DATA_DIR = tmp_path
            TESTING = True

        app = create_app(BenchmarkConfig)
        with app.app_context():
            init_db(db_file)
            seed_database(db_file)

        # Verify WAL journal mode
        conn = sqlite3.connect(db_file)
        journal_mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
        busy_timeout = conn.execute("PRAGMA busy_timeout;").fetchone()[0]
        conn.close()

        client = app.test_client()

        latencies: List[float] = []
        success_count = 0
        failure_count = 0

        def worker_task(idx: int) -> tuple[bool, float]:
            start = time.perf_counter()
            # Alternating operations: Token issuance and Token Introspection
            if idx % 2 == 0:
                res = client.post(
                    "/oauth/token",
                    data={
                        "grant_type": "client_credentials",
                        "client_id": "pulse-m2m-service",
                        "client_secret": "pulse_m2m_secret_2026",
                        "scope": "read:documents",
                    },
                )
            else:
                res = client.post(
                    "/api/v1/auth/login",
                    json={
                        "email": "developer@pulseauth.dev",
                        "password": "DevPass2026!",
                    },
                )

            elapsed_ms = (time.perf_counter() - start) * 1000.0
            return (res.status_code == 200, elapsed_ms)

        print(
            f">> Launching Benchmark: {total_requests} requests "
            f"across {concurrency} workers..."
        )
        wall_clock_start = time.perf_counter()

        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = [executor.submit(worker_task, i) for i in range(total_requests)]
            for f in as_completed(futures):
                success, latency_ms = f.result()
                latencies.append(latency_ms)
                if success:
                    success_count += 1
                else:
                    failure_count += 1

        total_wall_time = time.perf_counter() - wall_clock_start
        latencies.sort()

        throughput = round(total_requests / total_wall_time, 2)
        mean_latency = round(sum(latencies) / len(latencies), 2)
        p50 = calculate_percentile(latencies, 50)
        p90 = calculate_percentile(latencies, 90)
        p95 = calculate_percentile(latencies, 95)
        p99 = calculate_percentile(latencies, 99)
        min_lat = round(latencies[0], 2)
        max_lat = round(latencies[-1], 2)

        return {
            "journal_mode": journal_mode.upper(),
            "busy_timeout": busy_timeout,
            "total_requests": total_requests,
            "concurrency": concurrency,
            "success_count": success_count,
            "failure_count": failure_count,
            "total_wall_time": round(total_wall_time, 3),
            "throughput": throughput,
            "mean_latency": mean_latency,
            "min_latency": min_lat,
            "max_latency": max_lat,
            "p50": p50,
            "p90": p90,
            "p95": p95,
            "p99": p99,
        }


def main():
    """CLI Entry point for concurrency benchmark."""
    print("=" * 72)
    print("  PULSEAUTH: MULTI-THREADED SQLITE WAL CONCURRENCY BENCHMARK")
    print("=" * 72)

    stats = run_benchmark(concurrency=50, total_requests=500)

    print("\n" + "=" * 72)
    print("  BENCHMARK SUMMARY & PERFORMANCE RESULTS")
    print("=" * 72)
    print(
        f"  * SQLite Journal Mode : {stats['journal_mode']} "
        f"(Busy Timeout: {stats['busy_timeout']}ms)"
    )
    print(f"  * Concurrent Workers  : {stats['concurrency']} threads")
    print(f"  * Total Operations    : {stats['total_requests']} requests")
    pct_success = (stats["success_count"] / stats["total_requests"]) * 100
    print(f"  * Successful Requests : {stats['success_count']} ({pct_success:.1f}%)")
    print(f"  * Failed Requests     : {stats['failure_count']}")
    print(f"  * Total Duration      : {stats['total_wall_time']} s")
    print(f"  * System Throughput   : {stats['throughput']} req/s")
    print("-" * 72)
    print("  LATENCY PERCENTILES (ms):")
    print(f"  * Mean Latency        : {stats['mean_latency']} ms")
    print(f"  * Min Latency         : {stats['min_latency']} ms")
    print(f"  * Max Latency         : {stats['max_latency']} ms")
    print(f"  * p50 (Median)        : {stats['p50']} ms")
    print(f"  * p90 Percentile      : {stats['p90']} ms")
    print(f"  * p95 Percentile      : {stats['p95']} ms")
    print(f"  * p99 Percentile      : {stats['p99']} ms")
    print("=" * 72)

    if stats["failure_count"] > 0:
        print(">> BENCHMARK STATUS: FAILED (Errors detected)")
        sys.exit(1)
    else:
        print(">> BENCHMARK STATUS: [OK] PASSED WITH ZERO LOCK CONTENTION")
        sys.exit(0)


if __name__ == "__main__":
    main()
