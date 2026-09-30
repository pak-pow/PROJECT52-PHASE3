from datetime import datetime
from app import create_app
from app.db import get_db

SEED_TASKS = [
    {
        "id": "task_seed_1",
        "title": "Install TaskPulse to Home Screen",
        "description": "Click the Install App button in header to run standalone.",
        "category": "work",
        "priority": "high",
        "completed": 0,
    },
    {
        "id": "task_seed_2",
        "title": "Test Offline Mode in DevTools",
        "description": (
            "Toggle network offline in browser DevTools and add a new task."
        ),
        "category": "work",
        "priority": "urgent",
        "completed": 0,
    },
    {
        "id": "task_seed_3",
        "title": "Review IndexedDB storage inspector",
        "description": (
            "Inspect quota usage and verify items persist across browser reloads."
        ),
        "category": "personal",
        "priority": "medium",
        "completed": 1,
    },
    {
        "id": "task_seed_4",
        "title": "Verify Service Worker Cache Lifecycle",
        "description": (
            "Inspect cache storage entries for app shell static assets."
        ),
        "category": "work",
        "priority": "low",
        "completed": 0,
    },
]


def seed_database():
    """Seeds baseline tasks into database if empty."""
    app = create_app()
    with app.app_context():
        db = get_db()
        cursor = db.execute("SELECT COUNT(*) as count FROM tasks")
        count = cursor.fetchone()["count"]

        if count == 0:
            now = datetime.utcnow().isoformat() + "Z"
            for task in SEED_TASKS:
                db.execute(
                    """
                    INSERT INTO tasks (
                        id, title, description, category, priority,
                        completed, created_at, updated_at, is_deleted
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
                    """,
                    (
                        task["id"],
                        task["title"],
                        task["description"],
                        task["category"],
                        task["priority"],
                        task["completed"],
                        now,
                        now,
                    ),
                )
            db.commit()
            print(f"[Seed] Successfully seeded {len(SEED_TASKS)} baseline tasks.")
        else:
            print(f"[Seed] Database already has {count} tasks. Skipping.")


if __name__ == "__main__":
    seed_database()
