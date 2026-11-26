"""Unit tests for CommentService threading, Gravatar, rate limiting, and moderation."""

import hashlib

import pytest

from app.models.post import PostDAO
from app.models.user import UserDAO
from app.services.comment_service import CommentService, RateLimitExceededError


def test_gravatar_url_and_ip_hashing() -> None:
    """Verify Gravatar MD5 normalization and deterministic SHA-256 IP hashing."""
    expected_md5 = hashlib.md5(b"reader@example.com").hexdigest()  # nosec B324
    url = CommentService.gravatar_url("  Reader@Example.COM ", size=64, default="mp")
    assert url == f"https://www.gravatar.com/avatar/{expected_md5}?s=64&d=mp"

    h1 = CommentService.hash_ip("192.168.1.10")
    h2 = CommentService.hash_ip(" 192.168.1.10 ")
    h3 = CommentService.hash_ip("192.168.1.11")
    assert h1 == h2
    assert h1 != h3
    assert len(h1) == 64


def test_submit_comment_validation_and_sanitization(empty_db_conn) -> None:
    """Verify comment input validation, HTML escaping, and parent post checks."""
    author = UserDAO.create(empty_db_conn, "writer", "w@example.com", "pw", "Writer")
    post = PostDAO.create(
        empty_db_conn, author["id"], "First Post", "Body", status="published"
    )
    other_post = PostDAO.create(
        empty_db_conn, author["id"], "Second Post", "Body 2", status="published"
    )

    with pytest.raises(ValueError, match="Author name is required"):
        CommentService.submit_comment(
            empty_db_conn, post["id"], "  ", "u@example.com", "Hello"
        )

    with pytest.raises(ValueError, match="valid email"):
        CommentService.submit_comment(
            empty_db_conn, post["id"], "Alice", "bad-email", "Hello"
        )

    with pytest.raises(ValueError, match="cannot be empty"):
        CommentService.submit_comment(
            empty_db_conn, post["id"], "Alice", "a@example.com", "   "
        )

    with pytest.raises(ValueError, match="does not exist"):
        CommentService.submit_comment(
            empty_db_conn, 99999, "Alice", "a@example.com", "Hello"
        )

    # Valid submission with XSS payload gets escaped
    comment = CommentService.submit_comment(
        empty_db_conn,
        post["id"],
        "<script>Alice</script>",
        "Alice@Example.com",
        "Nice post! <img src=x onerror=alert(1)>",
        ip_address="10.0.0.1",
        auto_approve=True,
    )
    assert comment["status"] == "approved"
    assert "&lt;script&gt;" in comment["author_name"]
    assert "&lt;img" in comment["body"]
    assert "author_email" not in comment
    assert "author_ip_hash" not in comment
    assert "gravatar.com/avatar/" in comment["gravatar_url"]

    # Parent belonging to another post is rejected
    with pytest.raises(ValueError, match="different post"):
        CommentService.submit_comment(
            empty_db_conn,
            other_post["id"],
            "Bob",
            "b@example.com",
            "Cross-post reply",
            parent_id=comment["id"],
        )


def test_threaded_comment_tree_and_public_redaction(empty_db_conn) -> None:
    """Verify nested reply tree assembly with Gravatar enrichment and privacy."""
    author = UserDAO.create(
        empty_db_conn, "writer2", "w2@example.com", "pw", "Writer Two"
    )
    post = PostDAO.create(
        empty_db_conn, author["id"], "Thread Post", "Body", status="published"
    )

    root = CommentService.submit_comment(
        empty_db_conn,
        post["id"],
        "Root User",
        "root@example.com",
        "Root comment",
        ip_address="10.0.0.2",
        auto_approve=True,
    )
    child = CommentService.submit_comment(
        empty_db_conn,
        post["id"],
        "Child User",
        "child@example.com",
        "Reply to root",
        ip_address="10.0.0.3",
        parent_id=root["id"],
        auto_approve=True,
    )
    CommentService.submit_comment(
        empty_db_conn,
        post["id"],
        "Grandchild User",
        "gc@example.com",
        "Nested reply",
        ip_address="10.0.0.4",
        parent_id=child["id"],
        auto_approve=True,
    )

    tree = CommentService.get_threaded_comments(empty_db_conn, post["id"])
    assert len(tree) == 1
    assert tree[0]["author_name"] == "Root User"
    assert "gravatar_url" in tree[0]
    assert "author_email" not in tree[0]
    assert len(tree[0]["replies"]) == 1
    assert tree[0]["replies"][0]["author_name"] == "Child User"
    assert len(tree[0]["replies"][0]["replies"]) == 1
    assert tree[0]["replies"][0]["replies"][0]["author_name"] == "Grandchild User"


def test_ip_rate_limiting(empty_db_conn) -> None:
    """Verify 5 comments per 10-minute window rate limit per IP hash."""
    author = UserDAO.create(
        empty_db_conn, "writer3", "w3@example.com", "pw", "Writer Three"
    )
    post = PostDAO.create(
        empty_db_conn, author["id"], "Rate Post", "Body", status="published"
    )

    for idx in range(5):
        CommentService.submit_comment(
            empty_db_conn,
            post["id"],
            f"Visitor {idx}",
            f"v{idx}@example.com",
            f"Comment number {idx}",
            ip_address="203.0.113.50",
        )

    allowed, remaining = CommentService.check_rate_limit(
        empty_db_conn, CommentService.hash_ip("203.0.113.50")
    )
    assert allowed is False
    assert remaining == 0

    with pytest.raises(RateLimitExceededError, match="Rate limit exceeded"):
        CommentService.submit_comment(
            empty_db_conn,
            post["id"],
            "Spammer",
            "spam@example.com",
            "Sixth comment",
            ip_address="203.0.113.50",
        )

    # Different IP is unaffected
    other = CommentService.submit_comment(
        empty_db_conn,
        post["id"],
        "Other Visitor",
        "other@example.com",
        "Allowed comment",
        ip_address="203.0.113.99",
    )
    assert other["status"] == "pending"


def test_moderation_state_machine_and_bulk_moderate(empty_db_conn) -> None:
    """Verify comment moderation transitions, queue listing, and bulk actions."""
    author = UserDAO.create(
        empty_db_conn, "writer4", "w4@example.com", "pw", "Writer Four"
    )
    post = PostDAO.create(
        empty_db_conn, author["id"], "Mod Post", "Body", status="published"
    )

    c1 = CommentService.submit_comment(
        empty_db_conn, post["id"], "User 1", "u1@example.com", "Pending 1"
    )
    c2 = CommentService.submit_comment(
        empty_db_conn, post["id"], "User 2", "u2@example.com", "Pending 2"
    )

    queue = CommentService.list_moderation_queue(empty_db_conn, status="pending")
    assert len(queue) == 2
    assert queue[0]["post_title"] == "Mod Post"

    # Transition pending -> approved -> flagged -> rejected
    approved = CommentService.moderate_comment(empty_db_conn, c1["id"], "approved")
    assert approved["status"] == "approved"

    # Idempotent transition
    same = CommentService.moderate_comment(empty_db_conn, c1["id"], "approved")
    assert same["status"] == "approved"

    flagged = CommentService.moderate_comment(empty_db_conn, c1["id"], "flagged")
    assert flagged["status"] == "flagged"

    # Invalid transition: flagged -> pending is disallowed
    with pytest.raises(ValueError, match="not allowed"):
        CommentService.moderate_comment(empty_db_conn, c1["id"], "pending")

    # Invalid status name
    with pytest.raises(ValueError, match="Invalid moderation status"):
        CommentService.moderate_comment(empty_db_conn, c1["id"], "deleted")

    # Bulk moderate c1 (flagged->rejected) and c2 (pending->rejected) + nonexistent ID
    summary = CommentService.bulk_moderate(
        empty_db_conn, [c1["id"], c2["id"], 99999], "rejected"
    )
    assert summary["updated"] == [c1["id"], c2["id"]]
    assert len(summary["failed"]) == 1
    assert summary["failed"][0]["comment_id"] == 99999

    assert CommentService.delete_comment(empty_db_conn, c1["id"]) is True
    assert CommentService.delete_comment(empty_db_conn, c1["id"]) is False
