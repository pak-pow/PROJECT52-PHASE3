import configparser
import os
import subprocess
import sys
try:
    import tomllib
except ImportError:
    import tomli as tomllib
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent


def test_flake8_config_exists_and_valid():
    """Verify .flake8 configuration file exists and contains valid settings."""
    flake8_path = BACKEND_DIR / ".flake8"
    assert flake8_path.exists(), ".flake8 configuration file is missing"

    config = configparser.ConfigParser()
    config.read(flake8_path)
    assert "flake8" in config.sections()
    assert int(config["flake8"]["max-line-length"]) == 88
    assert "E203" in config["flake8"]["extend-ignore"]


def test_pyproject_toml_exists_and_valid():
    """Verify pyproject.toml exists and configures black, isort, and bandit."""
    pyproject_path = BACKEND_DIR / "pyproject.toml"
    assert pyproject_path.exists(), "pyproject.toml is missing"

    with open(pyproject_path, "rb") as f:
        data = tomllib.load(f)

    assert "tool" in data
    assert "black" in data["tool"]
    assert data["tool"]["black"]["line-length"] == 88
    assert "isort" in data["tool"]
    assert data["tool"]["isort"]["profile"] == "black"
    assert "bandit" in data["tool"]


def test_coveragerc_exists_and_enforces_90_percent():
    """Verify .coveragerc requires minimum 90% branch and statement coverage."""
    coveragerc_path = BACKEND_DIR / ".coveragerc"
    assert coveragerc_path.exists(), ".coveragerc is missing"

    config = configparser.ConfigParser()
    config.read(coveragerc_path)
    assert "report" in config.sections()
    assert float(config["report"]["fail_under"]) >= 90.0
    assert config["run"].getboolean("branch") is True


def test_codebase_passes_flake8_linting():
    """Programmatically verify entire codebase passes Flake8 without errors."""
    cmd = [
        sys.executable,
        "-m",
        "flake8",
        str(BACKEND_DIR / "app"),
        str(BACKEND_DIR / "tests"),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert (
        result.returncode == 0
    ), f"Flake8 linting check failed:\n{result.stdout}\n{result.stderr}"


def test_codebase_passes_bandit_security_audit():
    """Programmatically verify application code passes Bandit security scan."""
    cmd = [
        sys.executable,
        "-m",
        "bandit",
        "-r",
        str(BACKEND_DIR / "app"),
        "-ll",  # Medium and High severity checks
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert (
        result.returncode == 0
    ), f"Bandit security scan detected issues:\n{result.stdout}\n{result.stderr}"


def test_no_forbidden_dangerous_patterns_in_app():
    """Static AST scan to ensure no eval, exec, or raw shell=True calls exist in app."""
    forbidden_tokens = ["eval(", "exec(", "shell=True"]
    app_dir = BACKEND_DIR / "app"

    for root, _, files in os.walk(app_dir):
        for file in files:
            if file.endswith(".py"):
                file_path = Path(root) / file
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    for token in forbidden_tokens:
                        assert (
                            token not in content
                        ), f"Forbidden security token '{token}' found in {file_path}"
