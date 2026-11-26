"""Threaded comment service with moderation, Gravatar, and IP rate limiting."""

import hashlib
import html
import re
import sqlite3
from typing import Any, Dict, List, Optional, Set, Tuple

from app.models.comment import CommentDAO
from app.models.post import PostDAO

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class RateLimitExceededError(ValueError):
    """Raised when a visitor exceeds the comment submission rate limit."""


class CommentService:
    """Service for threaded comments, Gravatar avatars, and moderation."""

    VALID_STATUSES: Set[str] = {"pending", "approved", "rejected", "flagged"}
    ALLOWED_TRANSITIONS: Dict[str, Set[str]] = {
        "pending": {"approved", "rejected", "flagged"},
        "approved": {"rejected", "flagged", "pending"},
        "flagged": {"approved", "rejected"},
        "rejected": {"approved", "pending"},
    }
    MAX_BODY_LENGTH = 5000

    @staticmethod
    def hash_ip(ip_address: str, salt: str = "pulsepress_ip_salt") -> str:
        """Compute deterministic SHA-256 hash of a visitor IP address."""
        raw = f"{salt}:{ip_address.strip()}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    @staticmethod
    def gravatar_url(email: str, size: int = 80, default: str = "identicon") -> str:
        """Generate a Gravatar avatar URL from an email address MD5 hash."""
        normalized = email.strip().lower().encode("utf-8")
        digest = hashlib.md5(normalized, usedforsecurity=False).hexdigest()
        return f"https://www.gravatar.com/avatar/{digest}?s={size}&d={default}"

    @staticmethod
    def check_rate_limit(
        conn: sqlite3.Connection,
        ip_hash: str,
        window_minutes: int = 10,
        max_comments: int = 5,
    ) -> Tuple[bool, int]:
        """Check whether an IP hash is within the comment submission rate limit."""
        recent_count = CommentDAO.count_recent_from_ip(
            conn, ip_hash, minutes=window_minutes
        )
        remaining = max(0, max_comments - recent_count)
        return recent_count < max_comments, remaining

    @staticmethod
    def _enrich_public_comment(comment: Dict[str, Any]) -> Dict[str, Any]:
        """Attach Gravatar URL and redact private email/IP fields for public views."""
        enriched = dict(comment)
        email = enriched.pop("author_email", "")
        enriched.pop("author_ip_hash", None)
        enriched["gravatar_url"] = CommentService.gravatar_url(email)

        if "replies" in enriched and isinstance(enriched["replies"], list):
            enriched["replies"] = [
                CommentService._enrich_public_comment(reply)
                for reply in enriched["replies"]
            ]
        return enriched

    @staticmethod
    def submit_comment(
        conn: sqlite3.Connection,
        post_id: int,
        author_name: str,
        author_email: str,
        body: str,
        ip_address: str = "127.0.0.1",
        parent_id: Optional[int] = None,
        auto_approve: bool = False,
        window_minutes: int = 10,
        max_comments: int = 5,
    ) -> Dict[str, Any]:
        """Validate, rate-limit, sanitize, and persist a new visitor comment."""
        clean_name = author_name.strip()
        clean_email = author_email.strip().lower()
        clean_body = body.strip()

        if not clean_name:
            raise ValueError("Author name is required.")
        if len(clean_name) > 100:
            raise ValueError("Author name must be 100 characters or fewer.")
        if not EMAIL_REGEX.match(clean_email):
            raise ValueError("A valid email address is required.")
        if not clean_body:
            raise ValueError("Comment body cannot be empty.")
        if len(clean_body) > CommentService.MAX_BODY_LENGTH:
            raise ValueError(
                f"Comment body exceeds maximum length of "
                f"{CommentService.MAX_BODY_LENGTH} characters."
            )

        post = PostDAO.get_by_id(conn, post_id)
        if not post:
            raise ValueError(f"Post with ID {post_id} does not exist.")

        if parent_id is not None:
            parent = CommentDAO.get_by_id(conn, parent_id)
            if not parent:
                raise ValueError(f"Parent comment {parent_id} does not exist.")
            if parent["post_id"] != post_id:
                raise ValueError("Parent comment belongs to a different post.")

        ip_hash = CommentService.hash_ip(ip_address)
        allowed, _ = CommentService.check_rate_limit(
            conn,
            ip_hash,
            window_minutes=window_minutes,
            max_comments=max_comments,
        )
        if not allowed:
            raise RateLimitExceededError(
                f"Rate limit exceeded: max {max_comments} comments per "
                f"{window_minutes} minutes."
            )

        safe_name = html.escape(clean_name)
        safe_body = html.escape(clean_body)
        initial_status = "approved" if auto_approve else "pending"

        created = CommentDAO.create(
            conn=conn,
            post_id=post_id,
            author_name=safe_name,
            author_email=clean_email,
            author_ip_hash=ip_hash,
            body=safe_body,
            parent_id=parent_id,
            status=initial_status,
        )
        return CommentService._enrich_public_comment(created)

    @staticmethod
    def get_threaded_comments(
        conn: sqlite3.Connection,
        post_id: int,
        status: Optional[str] = "approved",
    ) -> List[Dict[str, Any]]:
        """Retrieve nested comment threads enriched with Gravatar URLs."""
        tree = CommentDAO.get_threaded_tree(conn, post_id, status=status)
        return [CommentService._enrich_public_comment(root) for root in tree]

    @staticmethod
    def moderate_comment(
        conn: sqlite3.Connection, comment_id: int, new_status: str
    ) -> Dict[str, Any]:
        """Transition a comment through the moderation state machine."""
        if new_status not in CommentService.VALID_STATUSES:
            raise ValueError(f"Invalid moderation status: '{new_status}'.")

        comment = CommentDAO.get_by_id(conn, comment_id)
        if not comment:
            raise ValueError(f"Comment {comment_id} not found.")

        current_status = comment["status"]
        if current_status == new_status:
            return comment

        allowed_targets = CommentService.ALLOWED_TRANSITIONS.get(current_status, set())
        if new_status not in allowed_targets:
            raise ValueError(
                f"Transition from '{current_status}' to '{new_status}' is not allowed."
            )

        updated = CommentDAO.update_status(conn, comment_id, new_status)
        return updated  # type: ignore

    @staticmethod
    def bulk_moderate(
        conn: sqlite3.Connection, comment_ids: List[int], new_status: str
    ) -> Dict[str, Any]:
        """Moderate a batch of comments and return updated/failed summary."""
        if new_status not in CommentService.VALID_STATUSES:
            raise ValueError(f"Invalid moderation status: '{new_status}'.")

        updated_ids: List[int] = []
        failed: List[Dict[str, Any]] = []

        for cid in comment_ids:
            try:
                CommentService.moderate_comment(conn, cid, new_status)
                updated_ids.append(cid)
            except ValueError as exc:
                failed.append({"comment_id": cid, "error": str(exc)})

        return {"updated": updated_ids, "failed": failed}

    @staticmethod
    def list_moderation_queue(
        conn: sqlite3.Connection,
        status: str = "pending",
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """List comments filtered by moderation status for admin review."""
        if status not in CommentService.VALID_STATUSES:
            raise ValueError(f"Invalid moderation status: '{status}'.")

        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT c.id, c.post_id, c.parent_id, c.author_name, c.author_email,
                   c.body, c.status, c.created_at, p.title AS post_title,
                   p.slug AS post_slug
            FROM comments c
            JOIN posts p ON c.post_id = p.id
            WHERE c.status = ?
            ORDER BY c.created_at DESC
            LIMIT ?;
            """,
            (status, limit),
        )
        rows = []
        for row in cursor.fetchall():
            item = dict(row)
            item["gravatar_url"] = CommentService.gravatar_url(
                item.get("author_email", "")
            )
            rows.append(item)
        return rows

    @staticmethod
    def delete_comment(conn: sqlite3.Connection, comment_id: int) -> bool:
        """Delete a comment and cascade its child replies."""
        return CommentDAO.delete(conn, comment_id)
