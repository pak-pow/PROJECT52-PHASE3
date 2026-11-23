"""Tests for URL slug generation and collision avoidance service."""

from app.services.slug_service import (
    ensure_unique_slug,
    generate_slug,
    generate_unique_slug_for_db,
)


def test_generate_slug_basic():
    """Verify standard text transforms into lowercase hyphenated slug."""
    title = "Hello World! Building Web Apps in 2026."
    slug = generate_slug(title)
    assert slug == "hello-world-building-web-apps-in-2026"


def test_generate_slug_unicode_transliteration():
    """Verify unicode characters are transliterated to ASCII."""
    title = "Café & Crème Brûlée: A Guide to Zürich"
    slug = generate_slug(title)
    assert slug == "cafe-creme-brulee-a-guide-to-zurich"


def test_generate_slug_empty_and_symbols():
    """Verify empty or symbol-only inputs fallback to untitled."""
    assert generate_slug("") == "untitled"
    assert generate_slug("??? !!! $$$") == "untitled"


def test_generate_slug_max_length_truncation():
    """Verify slug length is clamped to max_length at hyphen boundary."""
    long_title = "This is a very long blog post title that exceeds the normal limit"
    slug = generate_slug(long_title, max_length=25)
    assert len(slug) <= 25
    assert not slug.endswith("-")


def test_ensure_unique_slug_increments_counter():
    """Verify numeric suffixes are appended for duplicate slug names."""
    existing = ["my-post", "my-post-1", "my-post-2"]
    assert ensure_unique_slug("my-post", existing) == "my-post-3"
    assert ensure_unique_slug("unique-post", existing) == "unique-post"


def test_generate_unique_slug_for_db(db_conn):
    """Verify collision resolution against database posts table."""
    # Seeded post has slug: building-a-production-grade-blog-engine-with-advanced-seo
    title = "Building a Production-Grade Blog Engine with Advanced SEO"
    new_slug = generate_unique_slug_for_db(db_conn, title)
    assert new_slug == "building-a-production-grade-blog-engine-with-advanced-seo-1"

    # Excluding post 1 returns original slug
    excluded_slug = generate_unique_slug_for_db(db_conn, title, exclude_post_id=1)
    assert excluded_slug == "building-a-production-grade-blog-engine-with-advanced-seo"
