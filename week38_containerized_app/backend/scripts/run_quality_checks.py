"""Automated runner for all 5 enterprise quality gates.

Executes Flake8, Black, isort, Bandit, and Pytest branch coverage (>=90%).
"""

import subprocess
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent

CHECKS = [
    (
        "FLAKE8 LINTER",
        ["flake8", "--max-line-length=88", "app", "tests", "scripts"],
    ),
    (
        "BLACK FORMATTER",
        ["black", "--check", "app", "tests", "scripts"],
    ),
    (
        "ISORT IMPORTS",
        ["isort", "--profile", "black", "--check-only", "app", "tests", "scripts"],
    ),
    (
        "BANDIT SECURITY",
        ["bandit", "-r", "app", "-ll", "-q"],
    ),
    (
        "PYTEST COVERAGE",
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/",
            "--cov=app",
            "--cov-branch",
            "--cov-report=term-missing",
            "--cov-fail-under=90",
        ],
    ),
]


def run_checks() -> int:
    """Execute all checks sequentially and print a summary table."""
    print("=" * 65)
    print("  DOCKER PULSE BACKEND: QUALITY GATES")
    print("=" * 65)

    all_passed = True
    results = []

    for name, cmd in CHECKS:
        print(f"\n>> Running {name}...")
        start = time.perf_counter()
        proc = subprocess.run(cmd, cwd=BACKEND_DIR)
        duration = round(time.perf_counter() - start, 2)

        if proc.returncode == 0:
            status = "[OK] PASSED"
            results.append((name, status, f"{duration}s"))
        else:
            status = "[FAIL] FAILED"
            results.append((name, status, f"{duration}s"))
            all_passed = False
            print(f"!! {name} failed with exit code {proc.returncode} !!")

    print("\n" + "=" * 65)
    print("  QUALITY GATES SUMMARY REPORT")
    print("=" * 65)
    for name, status, dur in results:
        print(f"  * {name:<18} : {status:<12} ({dur})")
    print("=" * 65)

    if all_passed:
        print(">> ALL QUALITY GATES PASSED! Safe to commit and containerize.\n")
        return 0
    else:
        print("!! ONE OR MORE QUALITY GATES FAILED! Please fix issues above.\n")
        return 1


if __name__ == "__main__":
    sys.exit(run_checks())
