from flask import Blueprint, jsonify, request
from app.models.deployment_model import DeploymentModel, PipelineRunModel

deployment_bp = Blueprint("deployment_bp", __name__)


@deployment_bp.route("/api/v1/deployments", methods=["GET"])
def list_deployments():
    """List recorded deployments with optional environment filter."""
    environment = request.args.get("environment")
    limit = request.args.get("limit", default=50, type=int)
    limit = min(max(limit, 1), 100)

    deployments = DeploymentModel.get_deployments(environment=environment, limit=limit)
    return (
        jsonify(
            {
                "count": len(deployments),
                "environment_filter": environment or "all",
                "deployments": deployments,
            }
        ),
        200,
    )


@deployment_bp.route("/api/v1/deployments", methods=["POST"])
def record_deployment():
    """Record a deployment event from GitHub Actions or pipeline runner."""
    data = request.get_json(silent=True) or {}

    service_name = data.get("service_name", "deployment-monitor")
    environment = data.get("environment")
    version = data.get("version")
    commit_hash = data.get("commit_hash")

    if not environment or not version or not commit_hash:
        err_msg = (
            "Missing required fields: 'environment', "
            "'version', and 'commit_hash' are required."
        )
        return jsonify({"error": err_msg}), 400

    if environment not in ["development", "staging", "production"]:
        err_msg = (
            f"Invalid environment '{environment}'. "
            "Must be 'development', 'staging', or 'production'."
        )
        return jsonify({"error": err_msg}), 400

    triggered_by = data.get("triggered_by", "pipeline-runner")
    status = data.get("status", "success")
    notes = data.get("notes")

    deployment = DeploymentModel.create_deployment(
        service_name=service_name,
        environment=environment,
        version=version,
        commit_hash=commit_hash,
        triggered_by=triggered_by,
        status=status,
        notes=notes,
    )

    return (
        jsonify(
            {
                "message": "Deployment recorded successfully.",
                "deployment": deployment,
            }
        ),
        201,
    )


@deployment_bp.route("/api/v1/pipeline-runs", methods=["GET"])
def list_pipeline_runs():
    """List recent CI/CD pipeline execution runs."""
    limit = request.args.get("limit", default=25, type=int)
    limit = min(max(limit, 1), 100)

    runs = PipelineRunModel.get_recent_runs(limit=limit)
    return (
        jsonify(
            {
                "count": len(runs),
                "runs": runs,
            }
        ),
        200,
    )


@deployment_bp.route("/api/v1/pipeline-runs", methods=["POST"])
def record_pipeline_run():
    """Record a completed CI/CD pipeline run with stage statuses."""
    data = request.get_json(silent=True) or {}

    workflow_name = data.get("workflow_name", "ci.yml")
    branch = data.get("branch", "main")
    commit_sha = data.get("commit_sha", "HEAD")
    lint_status = data.get("lint_status", "passed")
    security_status = data.get("security_status", "passed")
    test_status = data.get("test_status", "passed")
    build_status = data.get("build_status", "passed")
    deploy_status = data.get("deploy_status", "skipped")
    overall_status = data.get("overall_status", "success")
    duration_seconds = float(data.get("duration_seconds", 0.0))

    run = PipelineRunModel.record_run(
        workflow_name=workflow_name,
        branch=branch,
        commit_sha=commit_sha,
        lint_status=lint_status,
        security_status=security_status,
        test_status=test_status,
        build_status=build_status,
        deploy_status=deploy_status,
        overall_status=overall_status,
        duration_seconds=duration_seconds,
    )

    return (
        jsonify(
            {
                "message": "Pipeline run recorded successfully.",
                "run": run,
            }
        ),
        201,
    )
