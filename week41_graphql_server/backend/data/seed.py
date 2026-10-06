import sys
from datetime import datetime
from pathlib import Path

# Add backend directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402
from app.db import get_db  # noqa: E402

SEED_TECHNOLOGIES = [
    ("Python", "BACKEND", "python"),
    ("GraphQL", "BACKEND", "graphql"),
    ("React", "FRONTEND", "react"),
    ("TypeScript", "FRONTEND", "typescript"),
    ("Docker", "DEVOPS", "docker"),
    ("PostgreSQL", "DATABASE", "postgresql"),
    ("Redis", "DATABASE", "redis"),
    ("TensorFlow", "AI_ML", "tensorflow"),
]

SEED_USERS = [
    (
        "alex_dev",
        "alex@pulsegraph.io",
        "ADMIN",
        "Full-stack engineer building GraphQL APIs.",
    ),
    (
        "sarah_cloud",
        "sarah@pulsegraph.io",
        "DEVELOPER",
        "Cloud architect and DevOps specialist.",
    ),
    (
        "marcus_fe",
        "marcus@pulsegraph.io",
        "DEVELOPER",
        "Frontend enthusiast focusing on modern web performance.",
    ),
]


def seed_database():
    """Seeds baseline technologies and developers into SQLite database."""
    app = create_app()
    with app.app_context():
        db = get_db()
        cursor = db.execute("SELECT COUNT(*) as count FROM technologies")
        tech_count = cursor.fetchone()["count"]

        if tech_count == 0:
            for name, cat, icon in SEED_TECHNOLOGIES:
                db.execute(
                    """
                    INSERT INTO technologies (name, category, icon_slug)
                    VALUES (?, ?, ?)
                    """,
                    (name, cat, icon),
                )
            print(f"[Seed] Added {len(SEED_TECHNOLOGIES)} technologies.")

        cursor = db.execute("SELECT COUNT(*) as count FROM users")
        user_count = cursor.fetchone()["count"]

        if user_count == 0:
            now = datetime.utcnow().isoformat() + "Z"
            for username, email, role, bio in SEED_USERS:
                db.execute(
                    """
                    INSERT INTO users (
                        username, email, role, bio, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (username, email, role, bio, now, now),
                )
            print(f"[Seed] Added {len(SEED_USERS)} baseline users.")

        db.commit()


if __name__ == "__main__":
    seed_database()
