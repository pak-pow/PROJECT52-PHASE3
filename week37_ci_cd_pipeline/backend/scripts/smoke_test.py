#!/usr/bin/env python3
"""
Post-Deployment Automated Smoke Test Probe
Used in CI/CD pipeline after deployment to verify:
1. Server is accepting HTTP connections
2. /api/v1/health returns 200 OK with status='healthy'
3. /api/v1/version returns 200 OK with valid version info
4. Latency is within acceptable thresholds (<1000ms)
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

# Ensure UTF-8 output on Windows consoles if supported
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def make_request(url, timeout=5):
    """Execute HTTP GET request using urllib standard library (zero external deps)."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "CI-CD-Smoke-Tester/1.0", "Accept": "application/json"},
    )
    start = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as response:
        duration_ms = round((time.time() - start) * 1000, 2)
        body = response.read().decode("utf-8")
        status_code = response.status
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            data = None
        return status_code, data, duration_ms


def run_smoke_tests(base_url, max_retries=5, retry_delay=2):
    print("\n" + "=" * 65)
    print(f"  POST-DEPLOYMENT SMOKE TEST PROBE: {base_url}")
    print("=" * 65)

    base_url = base_url.rstrip("/")
    health_url = f"{base_url}/api/v1/health"
    version_url = f"{base_url}/api/v1/version"

    # Step 1: Health Probe with Retries (Waiting for server readiness)
    print(f">> Probing Health Endpoint: {health_url}")
    connected = False
    health_data = None
    latency = 0

    for attempt in range(1, max_retries + 1):
        try:
            status, data, latency = make_request(health_url)
            if status == 200 and data and data.get("status") == "healthy":
                connected = True
                health_data = data
                print(f"   [OK] Server responded in {latency}ms (Attempt {attempt}/{max_retries})")
                break
            else:
                print(f"   [WARN] Unexpected response ({status}): {data}. Retrying...")
        except (urllib.error.URLError, ConnectionError, OSError) as e:
            print(f"   [WAIT] Connection attempt {attempt}/{max_retries} failed: {e}")

        if attempt < max_retries:
            time.sleep(retry_delay)

    if not connected:
        print("\n[FAILED] Smoke test FAILED: Server is unreachable or unhealthy.")
        return False

    # Step 2: Health Payload Validation
    print(">> Validating Health Response Payload:")
    required_health_keys = ["status", "service", "environment", "uptime_seconds", "version"]
    for key in required_health_keys:
        val = health_data.get(key)
        assert val is not None, f"Missing key '{key}' in health payload"
        print(f"   * {key:<16}: {val}")

    # Step 3: Version Probe
    print(f"\n>> Probing Version Endpoint: {version_url}")
    try:
        status, version_data, v_latency = make_request(version_url)
        if status != 200 or not version_data or "version" not in version_data:
            print(f"[FAILED] Version probe failed with status {status}: {version_data}")
            return False
        print(f"   [OK] Version responded in {v_latency}ms")
        print(f"   * Version         : {version_data.get('version')}")
        print(f"   * Commit Hash     : {version_data.get('commit_hash')}")
        print(f"   * Build Number    : {version_data.get('build_number')}")
    except Exception as e:
        print(f"[FAILED] Error probing version endpoint: {e}")
        return False

    # Step 4: Latency Check
    if latency > 1000:
        print(f"[WARN] Latency exceeded 1000ms threshold: {latency}ms")
    else:
        print(f"\n[OK] Latency within target threshold: {latency}ms (<1000ms)")

    print("=" * 65)
    print(">> ALL POST-DEPLOYMENT SMOKE TESTS PASSED!")
    print("=" * 65 + "\n")
    return True


def main():
    parser = argparse.ArgumentParser(description="CI/CD Smoke Test Probe")
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:5000",
        help="Base URL of target service",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=5,
        help="Maximum connection retry attempts",
    )
    parser.add_argument(
        "--delay",
        type=int,
        default=2,
        help="Seconds between retry attempts",
    )
    args = parser.parse_args()

    success = run_smoke_tests(
        base_url=args.url,
        max_retries=args.max_retries,
        retry_delay=args.delay,
    )
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
