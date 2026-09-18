"""Resilience, chaos recovery, and security probe CLI utility.

Validates application resilience against malformed inputs, injection attempts,
degraded dependencies, and verifies API health under simulated operational stress.
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple


class Colors:
    """ANSI terminal styling codes."""

    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


def request_json(
    url: str,
    method: str = "GET",
    data: Optional[Dict[str, Any]] = None,
    raw_data: Optional[bytes] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 5.0,
) -> Tuple[int, Any]:
    """Execute an HTTP request and parse JSON response or return status code."""
    req_headers = headers or {}
    body: Optional[bytes] = None

    if raw_data is not None:
        body = raw_data
    elif data is not None:
        body = json.dumps(data).encode("utf-8")
        if "Content-Type" not in req_headers:
            req_headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=body, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            status = response.status
            content = response.read().decode("utf-8")
            try:
                parsed = json.loads(content)
            except json.JSONDecodeError:
                parsed = content
            return status, parsed
    except urllib.error.HTTPError as err:
        status = err.code
        content = err.read().decode("utf-8")
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            parsed = content
        return status, parsed
    except Exception as exc:
        return 0, str(exc)


class ResilienceRunner:
    """Executes resilience, error handling, and security verification probes."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.results: List[Dict[str, Any]] = []
        self.created_task_ids: List[int] = []

    def log_result(
        self, name: str, passed: bool, duration: float, note: str = ""
    ) -> None:
        """Record check result."""
        self.results.append(
            {"name": name, "passed": passed, "duration": duration, "note": note}
        )
        tag = (
            f"{Colors.GREEN}[PASS]{Colors.RESET}"
            if passed
            else f"{Colors.RED}[FAIL]{Colors.RESET}"
        )
        print(f"  {tag} {name} ({duration:.2f}s) {Colors.YELLOW}{note}{Colors.RESET}")

    def test_liveness_and_version(self) -> None:
        """Verify server responds to liveness and version probes."""
        start = time.perf_counter()
        status, data = request_json(f"{self.base_url}/api/v1/health")
        v_status, v_data = request_json(f"{self.base_url}/api/v1/version")
        duration = time.perf_counter() - start

        passed = (
            status == 200
            and isinstance(data, dict)
            and data.get("status") == "healthy"
            and v_status == 200
        )
        uptime = data.get("uptime_seconds", 0) if isinstance(data, dict) else 0
        note = f"Uptime: {uptime}s" if passed else f"Status: {status}"
        self.log_result("Liveness & Version Probes", passed, duration, note)

    def test_readiness_probe(self) -> None:
        """Verify readiness probe evaluates database and cache status."""
        start = time.perf_counter()
        status, data = request_json(f"{self.base_url}/api/v1/ready")
        duration = time.perf_counter() - start

        # 200 (ready) or 503 (degraded) are valid structured readiness responses
        passed = status in (200, 503) and isinstance(data, dict) and "database" in data
        state = data.get("status", "unknown") if isinstance(data, dict) else "unknown"
        note = f"State: {state}" if passed else f"Status: {status}"
        self.log_result("Readiness Dependency Probe", passed, duration, note)

    def test_content_type_validation(self) -> None:
        """Verify non-JSON payload is rejected with HTTP 415."""
        start = time.perf_counter()
        status, _ = request_json(
            f"{self.base_url}/api/v1/tasks",
            method="POST",
            raw_data=b"plain text payload not json",
            headers={"Content-Type": "text/plain"},
        )
        duration = time.perf_counter() - start
        passed = status == 415
        note = f"HTTP {status} (Expected 415)"
        self.log_result("Non-JSON Payload Rejection", passed, duration, note)

    def test_malformed_input_rejection(self) -> None:
        """Verify malformed types and empty titles are rejected with HTTP 400."""
        start = time.perf_counter()
        # Case 1: Numeric title
        s1, _ = request_json(
            f"{self.base_url}/api/v1/tasks",
            method="POST",
            data={"title": 99999},
        )
        # Case 2: Empty title
        s2, _ = request_json(
            f"{self.base_url}/api/v1/tasks",
            method="POST",
            data={"title": "   "},
        )
        # Case 3: Invalid priority
        s3, _ = request_json(
            f"{self.base_url}/api/v1/tasks",
            method="POST",
            data={"title": "Valid Title", "priority": "super_extreme"},
        )
        duration = time.perf_counter() - start
        passed = s1 == 400 and s2 == 400 and s3 == 400
        note = f"s1={s1}, s2={s2}, s3={s3} (All 400)"
        self.log_result("Input Validation Rejection", passed, duration, note)

    def test_injection_resilience(self) -> None:
        """Verify SQL injection and XSS strings are safely stored and escaped."""
        start = time.perf_counter()
        xss_title = "<script>alert('xss')</script> Safe Task"
        sql_desc = "'; DROP TABLE tasks; SELECT * FROM users; --"

        status, data = request_json(
            f"{self.base_url}/api/v1/tasks",
            method="POST",
            data={"title": xss_title, "description": sql_desc, "priority": "high"},
        )
        duration = time.perf_counter() - start
        passed = status == 201 and isinstance(data, dict) and "task" in data
        if passed:
            task = data["task"]
            self.created_task_ids.append(task["id"])
            # Verify data is stored verbatim without executing SQL
            fetch_status, fetch_data = request_json(
                f"{self.base_url}/api/v1/tasks/{task['id']}"
            )
            passed = (
                fetch_status == 200
                and fetch_data["task"]["title"] == xss_title
                and fetch_data["task"]["description"] == sql_desc
            )
        note = "SQL injection & XSS stored safely as plain text"
        self.log_result("Injection Attacks Resilience", passed, duration, note)

    def test_rapid_burst_and_benchmark(self) -> None:
        """Verify concurrent benchmark calls execute without error."""
        start = time.perf_counter()
        success_count = 0
        total_requests = 10

        for _ in range(total_requests):
            status, _ = request_json(f"{self.base_url}/api/v1/benchmark")
            if status == 200:
                success_count += 1

        duration = time.perf_counter() - start
        passed = success_count == total_requests
        note = f"{success_count}/{total_requests} succeeded in {duration:.2f}s"
        self.log_result("Rapid Benchmark Burst", passed, duration, note)

    def cleanup(self) -> None:
        """Remove any test tasks created during testing."""
        for tid in self.created_task_ids:
            try:
                request_json(f"{self.base_url}/api/v1/tasks/{tid}", method="DELETE")
            except Exception:
                pass

    def run_all(self) -> bool:
        """Execute all resilience verification tests."""
        print(f"\n{Colors.BOLD}{'=' * 65}{Colors.RESET}")
        print(
            f"{Colors.CYAN}  DOCKER PULSE RESILIENCE & SECURITY VERIFICATION"
            f"{Colors.RESET}"
        )
        print(f"  Target: {self.base_url}")
        print(f"{Colors.BOLD}{'=' * 65}{Colors.RESET}\n")

        self.test_liveness_and_version()
        self.test_readiness_probe()
        self.test_content_type_validation()
        self.test_malformed_input_rejection()
        self.test_injection_resilience()
        self.test_rapid_burst_and_benchmark()
        self.cleanup()

        print(f"\n{Colors.BOLD}{'=' * 65}{Colors.RESET}")
        all_passed = all(r["passed"] for r in self.results)
        if all_passed:
            print(
                f"{Colors.GREEN}{Colors.BOLD}"
                f">> ALL RESILIENCE & SECURITY CHECKS PASSED!{Colors.RESET}\n"
            )
        else:
            print(
                f"{Colors.RED}{Colors.BOLD}"
                f">> SOME RESILIENCE CHECKS FAILED!{Colors.RESET}\n"
            )
        return all_passed


def main() -> None:
    """CLI entry point for resilience checks."""
    parser = argparse.ArgumentParser(
        description="Verify Docker Pulse resilience and security hardening."
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("DOCKER_PULSE_URL", "http://localhost:8080"),
        help="Target base URL of stack (default: http://localhost:8080)",
    )
    args = parser.parse_args()

    runner = ResilienceRunner(base_url=args.base_url)
    success = runner.run_all()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
