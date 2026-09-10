#!/usr/bin/env python3
"""
Continuous Integration Quality Gate Runner
Executes:
1. Flake8 Linting & Style Check
2. Black Formatting Check
3. Bandit Static Security Analysis
4. Pytest Suite with Coverage Threshold Enforcement
"""

import os
import subprocess
import sys
import time
from pathlib import Path

# Ensure UTF-8 output on Windows consoles if supported
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

BACKEND_DIR = Path(__file__).resolve().parent.parent


def print_banner(stage_num, stage_name):
    print("\n" + "=" * 65)
    print(f"  [STAGE {stage_num}] {stage_name}")
    print("=" * 65)


def run_command(cmd, desc):
    start_time = time.time()
    print(f">> Running: {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
    )
    duration = round(time.time() - start_time, 2)

    if result.returncode == 0:
        print(f"[OK] {desc} passed in {duration}s")
        if result.stdout.strip():
            print(result.stdout.strip())
        return True, duration, result.stdout
    else:
        print(f"[FAILED] {desc} FAILED in {duration}s")
        if result.stdout.strip():
            print("STDOUT:\n", result.stdout.strip())
        if result.stderr.strip():
            print("STDERR:\n", result.stderr.strip())
        return False, duration, result.stderr or result.stdout


def main():
    print("\n" + "#" * 65)
    print("  CI/CD LOCAL QUALITY GATES RUNNER")
    print("#" * 65)

    all_passed = True
    results = {}

    # Stage 1: Flake8
    print_banner(1, "Flake8 PEP8 Linting Check")
    passed, dur, out = run_command(
        [sys.executable, "-m", "flake8", "app", "tests"],
        "Flake8 Linting",
    )
    results["flake8"] = (passed, dur)
    if not passed:
        all_passed = False

    # Stage 2: Black Formatting Check
    print_banner(2, "Black Code Formatting Check")
    passed, dur, out = run_command(
        [sys.executable, "-m", "black", "--check", "app", "tests"],
        "Black Formatting Check",
    )
    results["black"] = (passed, dur)
    if not passed:
        all_passed = False

    # Stage 3: isort Import Ordering Check
    print_banner(3, "isort Import Ordering Check")
    passed, dur, out = run_command(
        [sys.executable, "-m", "isort", "--check-only", "app", "tests"],
        "isort Import Ordering",
    )
    results["isort"] = (passed, dur)
    if not passed:
        all_passed = False

    # Stage 4: Bandit Security Audit
    print_banner(4, "Bandit Static Security Audit")
    passed, dur, out = run_command(
        [sys.executable, "-m", "bandit", "-r", "app", "-ll"],
        "Bandit Security Audit",
    )
    results["bandit"] = (passed, dur)
    if not passed:
        all_passed = False

    # Stage 5: Pytest Suite with Coverage
    print_banner(5, "Pytest Test Suite with Coverage")
    passed, dur, out = run_command(
        [
            sys.executable,
            "-m",
            "pytest",
            "--cov=app",
            "--cov-report=term-missing",
            "tests",
        ],
        "Pytest with Coverage",
    )
    results["pytest_cov"] = (passed, dur)
    if not passed:
        all_passed = False

    # Summary
    print("\n" + "=" * 65)
    print("  QUALITY GATES SUMMARY REPORT")
    print("=" * 65)
    for gate, (p, d) in results.items():
        status = "[OK] PASSED" if p else "[X] FAILED"
        print(f"  * {gate.upper():<12} : {status} ({d}s)")

    print("=" * 65)
    if all_passed:
        print(">> ALL QUALITY GATES PASSED! Safe to commit and push.")
        sys.exit(0)
    else:
        print(">> ONE OR MORE QUALITY GATES FAILED. Review errors above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
