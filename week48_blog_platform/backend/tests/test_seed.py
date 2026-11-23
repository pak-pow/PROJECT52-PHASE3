"""Tests for database seed pipeline and idempotency."""

from app.models.user import UserDAO
from data.seed import DEFAULT_POSTS, DEFAULT_TAGS, DEFAULT_USERS, seed_database


def test_default_seed_counts(db_conn):
    """Verify seed pipeline populates expected baseline data."""
    cursor = db_conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM users;")
    assert cursor.fetchone()[0] == len(DEFAULT_USERS)

    cursor.execute("SELECT COUNT(*) FROM tags;")
    assert cursor.fetchone()[0] == len(DEFAULT_TAGS)

    cursor.execute("SELECT COUNT(*) FROM posts;")
    assert cursor.fetchone()[0] == len(DEFAULT_POSTS)

    cursor.execute("SELECT COUNT(*) FROM comments;")
    assert cursor.fetchone()[0] >= 3


def test_seed_idempotency(db_conn):
    """Verify calling seed_database repeatedly does not duplicate rows."""
    cursor = db_conn.cursor()

    # Seed a second and third time
    seed_database(db_conn)
    seed_database(db_conn)

    cursor.execute("SELECT COUNT(*) FROM users;")
    assert cursor.fetchone()[0] == len(DEFAULT_USERS)

    cursor.execute("SELECT COUNT(*) FROM tags;")
    assert cursor.fetchone()[0] == len(DEFAULT_TAGS)

    cursor.execute("SELECT COUNT(*) FROM posts;")
    assert cursor.fetchone()[0] == len(DEFAULT_POSTS)


def test_seeded_users_can_authenticate(db_conn):
    """Verify seeded user password hashes match plain text credentials."""
    admin = UserDAO.get_by_username(db_conn, "admin")
    assert admin is not None
    assert UserDAO.verify_password(admin, "AdminPassword123!") is True
    assert UserDAO.verify_password(admin, "WrongPassword") is False
