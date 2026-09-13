"""Task management and benchmark REST endpoints."""

import json
import time
from datetime import datetime, timezone

from flask import Blueprint, current_app, jsonify, request

from app.cache import cache
from app.db import check_db_health
from app.models.task_model import TaskModel

task_bp = Blueprint("tasks", __name__)


@task_bp.route("/tasks", methods=["GET"])
def list_tasks():
    """List tasks with optional caching and filtering."""
    limit = min(request.args.get("limit", default=50, type=int), 100)
    offset = max(request.args.get("offset", default=0, type=int), 0)
    status = request.args.get("status")
    priority = request.args.get("priority")
    no_cache = request.args.get("no_cache", default="false").lower() == "true"

    db_url = current_app.config.get("DATABASE_URL")
    cache_key = f"tasks:list:{limit}:{offset}:{status}:{priority}"

    if not no_cache:
        cached_data = cache.get(cache_key)
        if cached_data:
            try:
                tasks = json.loads(cached_data)
                response = jsonify(
                    {"tasks": tasks, "count": len(tasks), "cached": True}
                )
                response.headers["X-Cache"] = "HIT"
                return response, 200
            except Exception:
                pass

    tasks = TaskModel.get_all(
        limit=limit,
        offset=offset,
        status=status,
        priority=priority,
        db_url=db_url,
    )

    if not no_cache:
        cache.set(cache_key, json.dumps(tasks, default=str), ttl=60)

    response = jsonify({"tasks": tasks, "count": len(tasks), "cached": False})
    response.headers["X-Cache"] = "MISS"
    return response, 200


@task_bp.route("/tasks", methods=["POST"])
def create_task():
    """Create a new task and invalidate cached collections."""
    data = request.get_json(silent=True) or {}
    title = data.get("title", "")
    description = data.get("description", "")
    priority = data.get("priority", "medium")
    status = data.get("status", "pending")
    source = data.get("source", "web")

    db_url = current_app.config.get("DATABASE_URL")

    try:
        task = TaskModel.create(
            title=title,
            description=description,
            priority=priority,
            status=status,
            source=source,
            db_url=db_url,
        )
    except ValueError as err:
        return jsonify({"error": str(err)}), 400

    # Invalidate cache
    cache.delete("tasks:summary")
    cache.delete("tasks:list:50:0:None:None")

    return jsonify({"message": "Task created successfully.", "task": task}), 201


@task_bp.route("/tasks/<int:task_id>", methods=["GET"])
def get_task(task_id: int):
    """Retrieve a single task by ID with caching."""
    db_url = current_app.config.get("DATABASE_URL")
    cache_key = f"task:{task_id}"

    cached_data = cache.get(cache_key)
    if cached_data:
        try:
            task = json.loads(cached_data)
            return jsonify({"task": task, "cached": True}), 200
        except Exception:
            pass

    task = TaskModel.get_by_id(task_id, db_url=db_url)
    if not task:
        return jsonify({"error": "Task not found."}), 404

    cache.set(cache_key, json.dumps(task, default=str), ttl=120)
    return jsonify({"task": task, "cached": False}), 200


@task_bp.route("/tasks/<int:task_id>", methods=["PUT"])
def update_task(task_id: int):
    """Update task attributes."""
    data = request.get_json(silent=True) or {}
    db_url = current_app.config.get("DATABASE_URL")

    try:
        updated = TaskModel.update(
            task_id=task_id,
            title=data.get("title"),
            description=data.get("description"),
            priority=data.get("priority"),
            status=data.get("status"),
            db_url=db_url,
        )
    except ValueError as err:
        return jsonify({"error": str(err)}), 400

    if not updated:
        return jsonify({"error": "Task not found."}), 404

    cache.delete(f"task:{task_id}")
    cache.delete("tasks:summary")
    cache.delete("tasks:list:50:0:None:None")

    return jsonify({"message": "Task updated successfully.", "task": updated}), 200


@task_bp.route("/tasks/<int:task_id>", methods=["DELETE"])
def delete_task(task_id: int):
    """Remove a task by ID."""
    db_url = current_app.config.get("DATABASE_URL")
    success = TaskModel.delete(task_id, db_url=db_url)
    if not success:
        return jsonify({"error": "Task not found."}), 404

    cache.delete(f"task:{task_id}")
    cache.delete("tasks:summary")
    cache.delete("tasks:list:50:0:None:None")

    return jsonify({"message": "Task deleted successfully.", "id": task_id}), 200


@task_bp.route("/tasks/summary", methods=["GET"])
def tasks_summary():
    """Return task counts by status and priority with caching."""
    db_url = current_app.config.get("DATABASE_URL")
    cache_key = "tasks:summary"

    cached = cache.get(cache_key)
    if cached:
        try:
            return jsonify({"summary": json.loads(cached), "cached": True}), 200
        except Exception:
            pass

    summary = TaskModel.get_summary(db_url=db_url)
    cache.set(cache_key, json.dumps(summary), ttl=30)
    return jsonify({"summary": summary, "cached": False}), 200


@task_bp.route("/benchmark", methods=["GET"])
def benchmark_performance():
    """Benchmark database query latency versus cache retrieval speed."""
    db_url = current_app.config.get("DATABASE_URL")

    # 1. Database Benchmark
    db_start = time.perf_counter()
    db_info = check_db_health(db_url)
    db_ms = round((time.perf_counter() - db_start) * 1000, 3)

    # 2. Cache Benchmark
    cache_key = "__benchmark_probe__"
    cache.set(cache_key, "bench_payload", ttl=10)
    cache_start = time.perf_counter()
    cache.get(cache_key)
    cache_ms = round((time.perf_counter() - cache_start) * 1000, 3)

    # Calculate speedup (prevent divide by zero)
    speedup = round(db_ms / max(cache_ms, 0.001), 1)

    return (
        jsonify(
            {
                "database": {
                    "engine": db_info.get("engine", "unknown"),
                    "status": db_info.get("status", "unknown"),
                    "latency_ms": db_ms,
                },
                "cache": {
                    "engine": cache.engine,
                    "latency_ms": cache_ms,
                },
                "speedup_factor": f"{speedup}x faster via cache",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ),
        200,
    )
