import json
from pathlib import Path
from scripts.pipeline_runner import PipelineRunner


def test_pipeline_runner_initialization():
    """Verify PipelineRunner initializes with correct default attributes."""
    runner = PipelineRunner(target_stage="lint", env_name="staging")
    assert runner.target_stage == "lint"
    assert runner.env_name == "staging"
    assert runner.generate_badges is True
    assert isinstance(runner.results, dict)


def test_pipeline_runner_stage_lint():
    """Verify stage_lint executes and records status and duration."""
    runner = PipelineRunner(target_stage="lint")
    passed = runner.stage_lint()
    assert passed is True
    assert "lint" in runner.results
    assert runner.results["lint"]["status"] == "passed"
    assert runner.results["lint"]["duration"] > 0


def test_pipeline_runner_stage_security():
    """Verify stage_security executes Bandit and records result."""
    runner = PipelineRunner(target_stage="security")
    passed = runner.stage_security()
    assert passed is True
    assert "security" in runner.results
    assert runner.results["security"]["status"] == "passed"


def test_pipeline_runner_stage_build(tmp_path, monkeypatch):
    """Verify stage_build creates tar.gz release bundle."""
    runner = PipelineRunner(target_stage="build")
    passed = runner.stage_build()
    assert passed is True
    assert "build" in runner.results
    assert runner.results["build"]["status"] == "passed"
    bundle_path = Path(runner.results["build"]["artifact"])
    assert bundle_path.exists()
    assert bundle_path.stat().st_size > 500


def test_pipeline_runner_stage_deploy(client):
    """Verify stage_deploy records deployment in database."""
    runner = PipelineRunner(target_stage="deploy", env_name="staging")
    passed = runner.stage_deploy()
    assert passed is True
    assert "deploy" in runner.results
    assert runner.results["deploy"]["status"] == "passed"
    assert runner.results["deploy"]["environment"] == "staging"


def test_pipeline_runner_write_report_and_badges(tmp_path):
    """Verify write_report creates JSON report with stage metadata."""
    runner = PipelineRunner(target_stage="lint")
    runner.results["lint"] = {"status": "passed", "duration": 0.45}
    runner.results["security"] = {"status": "passed", "duration": 0.32}

    runner.write_report(overall_success=True, total_duration=0.77)
    report_file = (
        Path(__file__).resolve().parent.parent / "reports" / "pipeline_report.json"
    )
    assert report_file.exists()

    with open(report_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["overall_status"] == "success"
    assert data["total_duration_seconds"] == 0.77
    assert "lint" in data["stages"]
    assert "security" in data["stages"]
