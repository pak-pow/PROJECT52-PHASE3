"""Automated quality gates runner for PulseMesh microservices.

Enforces Flake8 (88-char), Black, isort, Bandit AST security, and Pytest (>=90%).
"""

import subprocess
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent


def get_existing_cov_dirs() -> list[str]:
    """Return existing directories containing python code for coverage."""
    candidates = ["shared", "services", "gateway"]
    active = []
    for c in candidates:
        target = ROOT_DIR / c
        if target.exists() and any(target.rglob("*.py")):
            active.append(f"--cov={c}")
    return active


def get_checks() -> list[tuple[str, list[str]]]:
    """Construct dynamic checks based on current active directories."""
    check_dirs = []
    for d in ["shared", "services", "gateway", "tests", "scripts"]:
        target = ROOT_DIR / d
        if target.exists() and any(target.rglob("*.py")):
            check_dirs.append(d)

    bandit_dirs = []
    for d in ["shared", "services", "gateway"]:
        target = ROOT_DIR / d
        if target.exists() and any(target.rglob("*.py")):
            bandit_dirs.append(d)

    cov_flags = get_existing_cov_dirs()

    pytest_cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/",
        *cov_flags,
        "--cov-branch",
        "--cov-report=term-missing",
        "--cov-fail-under=90",
    ]

    checks = [
        ("FLAKE8 LINTER", ["flake8", *check_dirs]),
        ("BLACK FORMATTER", ["black", "--check", *check_dirs]),
        ("ISORT IMPORTS", ["isort", "--check-only", *check_dirs]),
    ]

    if bandit_dirs:
        checks.append(("BANDIT SECURITY", ["bandit", "-r", *bandit_dirs, "-ll", "-q"]))

    checks.append(("PYTEST COVERAGE", pytest_cmd))
    return checks


def run_checks() -> int:
    """Execute all quality gates sequentially and return non-zero on failure."""
    print("=" * 70)
    print("  PULSEMESH MICROSERVICES: 5-STAGE AUTOMATED QUALITY GATES")
    print("=" * 70)

    checks = get_checks()
    all_passed = True
    results = []

    for name, cmd in checks:
        print(f"\n>> Executing {name}...")
        start = time.perf_counter()
        proc = subprocess.run(cmd, cwd=ROOT_DIR)
        duration = round(time.perf_counter() - start, 2)

        if proc.returncode == 0:
            results.append((name, "[OK] PASSED", f"{duration}s"))
        else:
            results.append((name, "[FAILED]", f"{duration}s"))
            all_passed = False
            print(f">> ERROR: {name} failed with exit code {proc.returncode}!")
            break

    print("\n" + "=" * 70)
    print("  QUALITY GATES SUMMARY REPORT")
    print("=" * 70)
    for name, status, dur in results:
        print(f"  * {name:<20} : {status:<10} ({dur})")
    print("=" * 70)

    if all_passed:
        print(">> ALL QUALITY GATES PASSED! Safe to commit and deploy.\n")
        return 0
    else:
        print(">> QUALITY GATES FAILED! Please resolve errors before committing.\n")
        return 1


if __name__ == "__main__":
    sys.exit(run_checks())
