"""Collision-safe, unicode-aware URL slug generator service."""

import re
import sqlite3
import unicodedata
from typing import Optional, Sequence, Union


def generate_slug(
    text: str,
    separator: Union[str, int] = "-",
    max_length: int = 80,
) -> str:
    """Transform raw text into a clean, URL-safe slug."""
    if not text:
        return "untitled"

    # Support callers passing max_length as second positional argument
    sep = "-"
    if isinstance(separator, int):
        max_len = separator
    else:
        sep = str(separator) or "-"
        max_len = max_length

    # Normalize unicode characters to NFKD representation
    normalized = unicodedata.normalize("NFKD", text)
    # Strip non-ASCII characters
    ascii_text = normalized.encode("ascii", "ignore").decode("utf-8")

    # Lowercase and replace non-alphanumeric characters with separators
    clean = re.sub(r"[^a-zA-Z0-9\s-]", "", ascii_text).lower()
    slug = re.sub(r"[-\s]+", sep, clean).strip(sep)

    if not slug:
        return "untitled"

    # Truncate to max_len at separator boundary if possible
    if len(slug) > max_len:
        truncated = slug[:max_len].rstrip(sep)
        last_sep = truncated.rfind(sep)
        if last_sep > max_len // 2:
            slug = truncated[:last_sep]
        else:
            slug = truncated

    return slug or "untitled"


def ensure_unique_slug(base_slug: str, existing_slugs: Sequence[str]) -> str:
    """Append incrementing numeric suffix if slug already exists in sequence."""
    existing_set = set(existing_slugs)
    if base_slug not in existing_set:
        return base_slug

    counter = 1
    while True:
        candidate = f"{base_slug}-{counter}"
        if candidate not in existing_set:
            return candidate
        counter += 1


def generate_unique_slug_for_db(
    conn: sqlite3.Connection,
    title: str,
    exclude_post_id: Optional[int] = None,
    max_length: int = 80,
) -> str:
    """Generate a guaranteed-unique post slug against current SQLite database."""
    base_slug = generate_slug(title, max_length=max_length)

    query = "SELECT id, slug FROM posts WHERE slug = ? OR slug LIKE ?"
    params = [base_slug, f"{base_slug}-%"]
    cursor = conn.cursor()
    cursor.execute(query, params)
    rows = cursor.fetchall()

    existing = [
        row["slug"]
        for row in rows
        if exclude_post_id is None or row["id"] != exclude_post_id
    ]

    return ensure_unique_slug(base_slug, existing)
