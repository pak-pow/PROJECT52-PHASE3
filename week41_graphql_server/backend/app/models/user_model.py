from datetime import datetime

from app.db import get_db


def create_user(username, email, role="DEVELOPER", bio=""):
    """Inserts a new developer user into the database."""
    if not username or not username.strip():
        raise ValueError("Username cannot be empty.")
    if not email or not email.strip():
        raise ValueError("Email cannot be empty.")

    username = username.strip()
    email = email.strip()
    bio = (bio or "").strip()
    role = (role or "DEVELOPER").upper()

    valid_roles = {"DEVELOPER", "MAINTAINER", "ADMIN"}
    if role not in valid_roles:
        raise ValueError(
            f"Invalid role '{role}'. Allowed roles: {', '.join(sorted(valid_roles))}."
        )

    db = get_db()
    # Check for existing username or email
    cursor = db.execute(
        "SELECT id FROM users WHERE username = ? OR email = ?",
        (username, email),
    )
    if cursor.fetchone():
        raise ValueError("A user with that username or email already exists.")

    now = datetime.utcnow().isoformat() + "Z"
    cursor = db.execute(
        """
        INSERT INTO users (username, email, role, bio, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (username, email, role, bio, now, now),
    )
    db.commit()
    return get_user_by_id(cursor.lastrowid)


def get_user_by_id(user_id):
    """Retrieves a single user record by primary key id."""
    db = get_db()
    cursor = db.execute(
        """
        SELECT id, username, email, role, bio, created_at, updated_at
        FROM users
        WHERE id = ?
        """,
        (user_id,),
    )
    row = cursor.fetchone()
    return dict(row) if row else None


def get_user_by_username(username):
    """Retrieves a single user record by unique username."""
    db = get_db()
    cursor = db.execute(
        """
        SELECT id, username, email, role, bio, created_at, updated_at
        FROM users
        WHERE username = ?
        """,
        (username,),
    )
    row = cursor.fetchone()
    return dict(row) if row else None


def get_user_by_email(email):
    """Retrieves a single user record by unique email."""
    db = get_db()
    cursor = db.execute(
        """
        SELECT id, username, email, role, bio, created_at, updated_at
        FROM users
        WHERE email = ?
        """,
        (email,),
    )
    row = cursor.fetchone()
    return dict(row) if row else None


def list_users():
    """Retrieves all registered developer records ordered by id."""
    db = get_db()
    cursor = db.execute("""
        SELECT id, username, email, role, bio, created_at, updated_at
        FROM users
        ORDER BY id ASC
        """)
    return [dict(row) for row in cursor.fetchall()]


def update_user(user_id, username=None, email=None, role=None, bio=None):
    """Updates fields on an existing user."""
    user = get_user_by_id(user_id)
    if not user:
        return None

    db = get_db()
    new_username = username.strip() if username is not None else user["username"]
    new_email = email.strip() if email is not None else user["email"]
    new_bio = bio.strip() if bio is not None else user["bio"]
    new_role = role.upper() if role is not None else user["role"]

    valid_roles = {"DEVELOPER", "MAINTAINER", "ADMIN"}
    if new_role not in valid_roles:
        raise ValueError(f"Invalid role '{new_role}'.")

    # Check unique constraint collisions
    cursor = db.execute(
        "SELECT id FROM users WHERE (username = ? OR email = ?) AND id != ?",
        (new_username, new_email, user_id),
    )
    if cursor.fetchone():
        raise ValueError("Username or email already in use by another user.")

    now = datetime.utcnow().isoformat() + "Z"
    db.execute(
        """
        UPDATE users
        SET username = ?, email = ?, role = ?, bio = ?, updated_at = ?
        WHERE id = ?
        """,
        (new_username, new_email, new_role, new_bio, now, user_id),
    )
    db.commit()
    return get_user_by_id(user_id)


def delete_user(user_id):
    """Deletes a user record and cascades related records."""
    user = get_user_by_id(user_id)
    if not user:
        return False

    db = get_db()
    db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    db.commit()
    return True
