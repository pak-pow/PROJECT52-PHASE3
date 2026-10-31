"""Database seeding script for baseline documents."""

import sys
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.db.connection import get_db_connection, init_db  # noqa: E402


def seed_database() -> None:
    """Initialize schema and populate starter document."""
    init_db()

    with get_db_connection() as conn:
        cursor = conn.cursor()
        doc_id = "welcome-doc"
        title = "Welcome to PulsePad"
        initial_content = (
            "# Welcome to PulsePad\n\n"
            "This is a real-time collaborative document editor.\n"
            "Multiple users can edit this text simultaneously with zero conflicts.\n"
        )

        cursor.execute(
            """
            INSERT OR IGNORE INTO documents (id, title, content, version)
            VALUES (?, ?, ?, 0)
            """,
            (doc_id, title, initial_content),
        )
        cursor.execute(
            """
            INSERT OR IGNORE INTO snapshots (document_id, revision_num, content)
            VALUES (?, 0, ?)
            """,
            (doc_id, initial_content),
        )
        conn.commit()


if __name__ == "__main__":
    seed_database()
