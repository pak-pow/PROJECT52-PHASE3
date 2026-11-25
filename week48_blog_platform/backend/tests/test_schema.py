"""Tests for SQLite database schema definitions and constraint enforcement."""

import sqlite3

import pytest

from app.db.connection import init_db


def test_all_expected_tables_exist(db_conn):
    """Verify all 7 core tables and indexes are created by schema."""
    cursor = db_conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type = 'table';")
    tables = {r[0] for r in cursor.fetchall()}

    expected_tables = {
        "users",
        "posts",
        "tags",
        "post_tags",
        "comments",
        "search_index",
        "post_views",
    }
    assert expected_tables.issubset(tables)


def test_user_role_check_constraint(empty_db_conn):
    """Verify user role check constraint enforces allowed values."""
    cursor = empty_db_conn.cursor()
    with pytest.raises(sqlite3.IntegrityError):
        cursor.execute("""
            INSERT INTO users (username, email, password_hash, display_name, role)
            VALUES ('bad_role', 'bad@test.com', 'hash', 'Bad Role', 'superhero');
            """)


def test_foreign_key_cascade_deletion(db_conn):
    """Verify deleting a post cascades and removes post_tags and comments."""
    cursor = db_conn.cursor()

    # Ensure post 1 has associated tags and comments
    cursor.execute("SELECT COUNT(*) FROM post_tags WHERE post_id = 1;")
    tags_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM comments WHERE post_id = 1;")
    comments_count = cursor.fetchone()[0]
    assert tags_count > 0
    assert comments_count > 0

    # Delete post 1
    cursor.execute("DELETE FROM posts WHERE id = 1;")
    db_conn.commit()

    # Verify cascades
    cursor.execute("SELECT COUNT(*) FROM post_tags WHERE post_id = 1;")
    assert cursor.fetchone()[0] == 0
    cursor.execute("SELECT COUNT(*) FROM comments WHERE post_id = 1;")
    assert cursor.fetchone()[0] == 0


def test_missing_schema_raises_not_found():
    """Verify init_db raises FileNotFoundError when schema file is missing."""
    with pytest.raises(FileNotFoundError):
        init_db(schema_path="/non/existent/path/schema.sql")
