"""Data access layer for tasks and operational telemetry."""

from typing import Any, Dict, List, Optional

from app.db import execute_query

VALID_PRIORITIES = {"low", "medium", "high", "critical", "urgent"}
VALID_STATUSES = {"pending", "in_progress", "completed"}


class TaskModel:
    """Encapsulates CRUD queries and summary aggregations for tasks."""

    @staticmethod
    def create(
        title: str,
        description: str = "",
        priority: str = "medium",
        status: str = "pending",
        source: str = "web",
        db_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a new task record and return the inserted object."""
        clean_title = title.strip()
        if not clean_title:
            raise ValueError("Task title cannot be empty.")
        if len(clean_title) > 255:
            raise ValueError("Task title cannot exceed 255 characters.")

        clean_priority = priority.lower().strip()
        if clean_priority not in VALID_PRIORITIES:
            raise ValueError(
                f"Invalid priority '{priority}'. Must be one of {VALID_PRIORITIES}."
            )

        clean_status = status.lower().strip()
        if clean_status not in VALID_STATUSES:
            raise ValueError(
                f"Invalid status '{status}'. Must be one of {VALID_STATUSES}."
            )

        insert_sql = (
            "INSERT INTO tasks (title, description, priority, status, source) "
            "VALUES (?, ?, ?, ?, ?);"
        )
        task_id = execute_query(
            insert_sql,
            (clean_title, description.strip(), clean_priority, clean_status, source),
            db_url=db_url,
            commit=True,
        )

        task = TaskModel.get_by_id(task_id, db_url=db_url)
        if not task:
            # Fallback representation
            return {
                "id": task_id,
                "title": clean_title,
                "description": description.strip(),
                "priority": clean_priority,
                "status": clean_status,
                "source": source,
            }
        return task

    @staticmethod
    def get_by_id(
        task_id: int, db_url: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Retrieve a single task record by ID."""
        query = "SELECT * FROM tasks WHERE id = ?;"
        return execute_query(query, (task_id,), db_url=db_url, fetch_one=True)

    @staticmethod
    def get_all(
        limit: int = 50,
        offset: int = 0,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        db_url: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List tasks with optional filtering and pagination."""
        query = "SELECT * FROM tasks"
        conditions = []
        params = []

        if status:
            clean_status = status.lower().strip()
            if clean_status in VALID_STATUSES:
                conditions.append("status = ?")
                params.append(clean_status)

        if priority:
            clean_priority = priority.lower().strip()
            if clean_priority in VALID_PRIORITIES:
                conditions.append("priority = ?")
                params.append(clean_priority)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)  # nosec B608

        query += " ORDER BY id DESC LIMIT ? OFFSET ?;"
        params.extend([limit, offset])

        return execute_query(query, tuple(params), db_url=db_url, fetch_all=True)

    @staticmethod
    def update(
        task_id: int,
        title: Optional[str] = None,
        description: Optional[str] = None,
        priority: Optional[str] = None,
        status: Optional[str] = None,
        db_url: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Update an existing task."""
        existing = TaskModel.get_by_id(task_id, db_url=db_url)
        if not existing:
            return None

        updates = []
        params = []

        if title is not None:
            clean_title = title.strip()
            if not clean_title:
                raise ValueError("Task title cannot be empty.")
            if len(clean_title) > 255:
                raise ValueError("Task title cannot exceed 255 characters.")
            updates.append("title = ?")
            params.append(clean_title)

        if description is not None:
            updates.append("description = ?")
            params.append(description.strip())

        if priority is not None:
            clean_priority = priority.lower().strip()
            if clean_priority not in VALID_PRIORITIES:
                raise ValueError(f"Invalid priority '{priority}'.")
            updates.append("priority = ?")
            params.append(clean_priority)

        if status is not None:
            clean_status = status.lower().strip()
            if clean_status not in VALID_STATUSES:
                raise ValueError(f"Invalid status '{status}'.")
            updates.append("status = ?")
            params.append(clean_status)

        if not updates:
            return existing

        updates.append("updated_at = CURRENT_TIMESTAMP")
        query = f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?;"  # nosec B608
        params.append(task_id)

        execute_query(query, tuple(params), db_url=db_url, commit=True)
        return TaskModel.get_by_id(task_id, db_url=db_url)

    @staticmethod
    def delete(task_id: int, db_url: Optional[str] = None) -> bool:
        """Delete a task by ID. Returns True if deleted, False if not found."""
        existing = TaskModel.get_by_id(task_id, db_url=db_url)
        if not existing:
            return False

        execute_query(
            "DELETE FROM tasks WHERE id = ?;", (task_id,), db_url=db_url, commit=True
        )
        return True

    @staticmethod
    def get_summary(db_url: Optional[str] = None) -> Dict[str, Any]:
        """Aggregate task metrics by status and priority."""
        total_row = execute_query(
            "SELECT COUNT(*) as total FROM tasks;", db_url=db_url, fetch_one=True
        )
        total = total_row["total"] if total_row else 0

        status_rows = execute_query(
            "SELECT status, COUNT(*) as count FROM tasks GROUP BY status;",
            db_url=db_url,
            fetch_all=True,
        )
        by_status = {r["status"]: r["count"] for r in status_rows}

        priority_rows = execute_query(
            "SELECT priority, COUNT(*) as count FROM tasks GROUP BY priority;",
            db_url=db_url,
            fetch_all=True,
        )
        by_priority = {r["priority"]: r["count"] for r in priority_rows}

        return {
            "total_tasks": total,
            "by_status": {
                "pending": by_status.get("pending", 0),
                "in_progress": by_status.get("in_progress", 0),
                "completed": by_status.get("completed", 0),
            },
            "by_priority": {
                "low": by_priority.get("low", 0),
                "medium": by_priority.get("medium", 0),
                "high": by_priority.get("high", 0),
                "critical": by_priority.get("critical", 0),
            },
        }

    @staticmethod
    def record_metric(
        metric_name: str,
        metric_value: float,
        details: str = "",
        db_url: Optional[str] = None,
    ) -> int:
        """Record an operational latency or resource metric."""
        query = (
            "INSERT INTO ops_metrics (metric_name, metric_value, details) "
            "VALUES (?, ?, ?);"
        )
        return execute_query(
            query,
            (metric_name.strip(), float(metric_value), details.strip()),
            db_url=db_url,
            commit=True,
        )
