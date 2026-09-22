import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent


def run_command(cmd, desc):
    print(f"--- Running: {desc} ---")
    res = subprocess.run(cmd, cwd=str(BACKEND_DIR))
    if res.returncode != 0:
        print(f"[FAIL] {desc} returned non-zero exit code: {res.returncode}")
        return False
    print(f"[PASS] {desc}")
    return True


def main():
    checks = [
        (
            ["flake8", "--max-line-length=88", "app", "tests", "data", "scripts"],
            "Flake8 Linter",
        ),
        (
            ["black", "--check", "app", "tests", "data", "scripts"],
            "Black Code Formatter",
        ),
        (
            [
                "isort",
                "--check-only",
                "--profile",
                "black",
                "app",
                "tests",
                "data",
                "scripts",
            ],
            "isort Import Sorter",
        ),
        (
            ["bandit", "-r", "app", "-ll", "-q"],
            "Bandit Security Audit",
        ),
        (
            [
                sys.executable,
                "-m",
                "pytest",
                "--cov=app",
                "--cov-report=term-missing",
                "--cov-fail-under=90",
            ],
            "Pytest Suite with Coverage",
        ),
    ]

    failed = 0
    for cmd, desc in checks:
        success = run_command(cmd, desc)
        if not success:
            failed += 1

    print("\n==============================")
    print(f"Summary: {len(checks) - failed}/{len(checks)} checks passed.")
    print("==============================")

    if failed > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
