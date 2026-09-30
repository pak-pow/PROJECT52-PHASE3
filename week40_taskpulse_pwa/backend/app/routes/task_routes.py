from flask import Blueprint, jsonify, request

from app.models.task_model import TaskModel

task_bp = Blueprint("tasks", __name__)


@task_bp.route("/tasks", methods=["GET"])
def get_tasks():
    """Retrieve all active tasks, optionally filtered by category."""
    category = request.args.get("category")
    tasks = TaskModel.get_all(category=category)
    return jsonify({"status": "success", "data": tasks, "count": len(tasks)}), 200


@task_bp.route("/tasks", methods=["POST"])
def create_task():
    """Create a new task."""
    data = request.get_json(silent=True) or {}
    title = data.get("title", "").strip()
    if not title:
        return (
            jsonify({"status": "error", "message": "Task title is required"}),
            400,
        )

    task = TaskModel.create(data)
    return jsonify({"status": "success", "data": task}), 201


@task_bp.route("/tasks/<task_id>", methods=["GET"])
def get_task(task_id):
    """Retrieve a single task by ID."""
    task = TaskModel.get_by_id(task_id)
    if not task:
        return (
            jsonify({"status": "error", "message": "Task not found"}),
            404,
        )
    return jsonify({"status": "success", "data": task}), 200


@task_bp.route("/tasks/<task_id>", methods=["PUT"])
def update_task(task_id):
    """Update fields on an existing task."""
    data = request.get_json(silent=True) or {}
    updated = TaskModel.update(task_id, data)
    if not updated:
        return (
            jsonify({"status": "error", "message": "Task not found"}),
            404,
        )
    return jsonify({"status": "success", "data": updated}), 200


@task_bp.route("/tasks/<task_id>", methods=["DELETE"])
def delete_task(task_id):
    """Soft-delete a task."""
    success = TaskModel.delete(task_id)
    if not success:
        return (
            jsonify({"status": "error", "message": "Task not found"}),
            404,
        )
    return (
        jsonify({"status": "success", "message": "Task deleted", "id": task_id}),
        200,
    )
