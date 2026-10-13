"""Database seeding script for baseline documents."""

from app.db.connection import get_db_connection, init_db


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
        conn.commit()


if __name__ == "__main__":
    seed_database()
