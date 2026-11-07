"""Automated quality gates runner for PulseAuth backend.

Enforces Flake8 (88-char), Black, isort, Bandit AST security, and Pytest (>=90%).
"""

import subprocess
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent

CHECKS = [
    (
        "FLAKE8 LINTER",
        ["flake8", "app", "tests", "data", "scripts"],
    ),
    (
        "BLACK FORMATTER",
        ["black", "--check", "app", "tests", "data", "scripts"],
    ),
    (
        "ISORT IMPORTS",
        ["isort", "--check-only", "app", "tests", "data", "scripts"],
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
    """Execute all quality gates sequentially and return non-zero on failure."""
    print("=" * 70)
    print("  PULSEAUTH BACKEND: 5-STAGE AUTOMATED QUALITY GATES")
    print("=" * 70)

    all_passed = True
    results = []

    for name, cmd in CHECKS:
        print(f"\n>> Executing {name}...")
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

    print("\n" + "=" * 70)
    print("  QUALITY GATES SUMMARY REPORT")
    print("=" * 70)
    for name, status, dur in results:
        print(f"  * {name:<20} : {status:<12} ({dur})")
    print("=" * 70)

    if all_passed:
        print(">> ALL QUALITY GATES PASSED! Safe to commit and deploy.\n")
        return 0
    else:
        print("!! ONE OR MORE QUALITY GATES FAILED! Please review issues above.\n")
        return 1


if __name__ == "__main__":
    sys.exit(run_checks())
