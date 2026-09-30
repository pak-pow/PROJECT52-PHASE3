import uuid
from datetime import datetime

from app.db import get_db


class TaskModel:
    """Data access and business logic for tasks and sync mutations."""

    @staticmethod
    def _row_to_dict(row):
        """Converts an SQLite row to a task dictionary."""
        if not row:
            return None
        return {
            "id": row["id"],
            "title": row["title"],
            "description": row["description"] or "",
            "category": row["category"] or "personal",
            "priority": row["priority"] or "medium",
            "completed": bool(row["completed"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "is_deleted": bool(row["is_deleted"]),
        }

    @classmethod
    def get_all(cls, category=None, include_deleted=False):
        """Retrieve all active tasks, optionally filtered by category."""
        db = get_db()
        clauses = []
        params = []

        if not include_deleted:
            clauses.append("is_deleted = 0")

        if category and category != "all":
            clauses.append("category = ?")
            params.append(category)

        query = "SELECT * FROM tasks"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY updated_at DESC"

        cursor = db.execute(query, params)
        rows = cursor.fetchall()
        return [cls._row_to_dict(row) for row in rows]

    @classmethod
    def get_by_id(cls, task_id, include_deleted=False):
        """Retrieve a task by ID."""
        db = get_db()
        query = "SELECT * FROM tasks WHERE id = ?"
        params = [task_id]

        if not include_deleted:
            query += " AND is_deleted = 0"

        cursor = db.execute(query, params)
        row = cursor.fetchone()
        return cls._row_to_dict(row)

    @classmethod
    def create(cls, data):
        """Create a new task."""
        db = get_db()
        now = datetime.utcnow().isoformat() + "Z"

        task_id = data.get("id") or f"task_{uuid.uuid4().hex[:12]}"
        title = data.get("title", "").strip()
        description = data.get("description", "").strip()
        category = data.get("category", "personal")
        priority = data.get("priority", "medium")
        completed = 1 if data.get("completed") else 0
        created_at = data.get("created_at") or now
        updated_at = data.get("updated_at") or now
        is_deleted = 1 if data.get("is_deleted") else 0

        db.execute(
            """
            INSERT INTO tasks (
                id, title, description, category, priority,
                completed, created_at, updated_at, is_deleted
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                title,
                description,
                category,
                priority,
                completed,
                created_at,
                updated_at,
                is_deleted,
            ),
        )
        db.commit()
        return cls.get_by_id(task_id, include_deleted=True)

    @classmethod
    def update(cls, task_id, data):
        """Update an existing task."""
        db = get_db()
        existing = cls.get_by_id(task_id, include_deleted=True)
        if not existing:
            return None

        now = datetime.utcnow().isoformat() + "Z"
        title = data.get("title", existing["title"])
        description = data.get("description", existing["description"])
        category = data.get("category", existing["category"])
        priority = data.get("priority", existing["priority"])
        completed = 1 if data.get("completed", existing["completed"]) else 0
        updated_at = data.get("updated_at") or now
        is_deleted = 1 if data.get("is_deleted", existing["is_deleted"]) else 0

        db.execute(
            """
            UPDATE tasks SET
                title = ?,
                description = ?,
                category = ?,
                priority = ?,
                completed = ?,
                updated_at = ?,
                is_deleted = ?
            WHERE id = ?
            """,
            (
                title,
                description,
                category,
                priority,
                completed,
                updated_at,
                is_deleted,
                task_id,
            ),
        )
        db.commit()
        return cls.get_by_id(task_id, include_deleted=True)

    @classmethod
    def delete(cls, task_id, soft_delete=True):
        """Deletes a task (soft delete by default)."""
        db = get_db()
        existing = cls.get_by_id(task_id, include_deleted=True)
        if not existing:
            return False

        if soft_delete:
            now = datetime.utcnow().isoformat() + "Z"
            db.execute(
                "UPDATE tasks SET is_deleted = 1, updated_at = ? WHERE id = ?",
                (now, task_id),
            )
        else:
            db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))

        db.commit()
        return True

    @classmethod
    def batch_sync(cls, mutations):
        """
        Replays an array of offline mutations using Last-Write-Wins (LWW) conflict
        resolution based on mutation timestamps.
        """
        db = get_db()
        applied = []
        conflicts = 0

        for m in mutations:
            action = m.get("action", "").upper()
            entity_id = m.get("entity_id")
            payload = m.get("payload", {})
            timestamp = m.get("timestamp") or (datetime.utcnow().isoformat() + "Z")

            if not entity_id or not action:
                continue

            existing = cls.get_by_id(entity_id, include_deleted=True)

            # Conflict Detection: LWW comparison
            if existing and existing["updated_at"] > timestamp:
                # Existing server record is newer than incoming client mutation
                conflicts += 1
                db.execute(
                    """
                    INSERT INTO sync_logs (
                        action, entity_id, status, created_at
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (action, entity_id, "CONFLICT_REJECTED", timestamp),
                )
                continue

            if action == "CREATE":
                if not existing:
                    cls.create(
                        {
                            "id": entity_id,
                            "title": payload.get("title", "Untitled Task"),
                            "description": payload.get("description", ""),
                            "category": payload.get("category", "personal"),
                            "priority": payload.get("priority", "medium"),
                            "completed": payload.get("completed", False),
                            "created_at": payload.get("created_at") or timestamp,
                            "updated_at": timestamp,
                            "is_deleted": 0,
                        }
                    )
                else:
                    cls.update(
                        entity_id,
                        {
                            "title": payload.get("title", existing["title"]),
                            "description": payload.get(
                                "description", existing["description"]
                            ),
                            "category": payload.get("category", existing["category"]),
                            "priority": payload.get("priority", existing["priority"]),
                            "completed": payload.get(
                                "completed", existing["completed"]
                            ),
                            "updated_at": timestamp,
                            "is_deleted": 0,
                        },
                    )
                applied.append({"action": action, "id": entity_id})

            elif action == "UPDATE":
                if existing:
                    cls.update(
                        entity_id,
                        {
                            "title": payload.get("title", existing["title"]),
                            "description": payload.get(
                                "description", existing["description"]
                            ),
                            "category": payload.get("category", existing["category"]),
                            "priority": payload.get("priority", existing["priority"]),
                            "completed": payload.get(
                                "completed", existing["completed"]
                            ),
                            "updated_at": timestamp,
                        },
                    )
                else:
                    cls.create(
                        {
                            "id": entity_id,
                            "title": payload.get("title", "Untitled Task"),
                            "description": payload.get("description", ""),
                            "category": payload.get("category", "personal"),
                            "priority": payload.get("priority", "medium"),
                            "completed": payload.get("completed", False),
                            "created_at": timestamp,
                            "updated_at": timestamp,
                        }
                    )
                applied.append({"action": action, "id": entity_id})

            elif action == "TOGGLE":
                completed_val = payload.get("completed", True)
                if existing:
                    cls.update(
                        entity_id,
                        {
                            "completed": completed_val,
                            "updated_at": timestamp,
                        },
                    )
                else:
                    cls.create(
                        {
                            "id": entity_id,
                            "title": "Untitled Task",
                            "completed": completed_val,
                            "created_at": timestamp,
                            "updated_at": timestamp,
                        }
                    )
                applied.append({"action": action, "id": entity_id})

            elif action == "DELETE":
                if existing:
                    db.execute(
                        """
                        UPDATE tasks SET is_deleted = 1, updated_at = ?
                        WHERE id = ?
                        """,
                        (timestamp, entity_id),
                    )
                    db.commit()
                applied.append({"action": action, "id": entity_id})

            db.execute(
                """
                INSERT INTO sync_logs (
                    action, entity_id, status, created_at
                ) VALUES (?, ?, ?, ?)
                """,
                (action, entity_id, "APPLIED", timestamp),
            )

        db.commit()
        return {
            "processed": len(applied),
            "applied": applied,
            "conflicts": conflicts,
        }

    @classmethod
    def get_delta(cls, since_timestamp=None):
        """Retrieve tasks modified or deleted after a given timestamp."""
        db = get_db()
        if since_timestamp:
            cursor = db.execute(
                """
                SELECT * FROM tasks
                WHERE updated_at > ?
                ORDER BY updated_at ASC
                """,
                (since_timestamp,),
            )
        else:
            cursor = db.execute("SELECT * FROM tasks ORDER BY updated_at ASC")
        rows = cursor.fetchall()
        return [cls._row_to_dict(row) for row in rows]
