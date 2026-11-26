"""Unit tests for TagService taxonomy, tag cloud weighting, and Jaccard similarity."""

import pytest

from app.models.post import PostDAO
from app.models.tag import TagDAO
from app.models.user import UserDAO
from app.services.tag_service import TagService


def test_create_tag_and_duplicate_rejection(empty_db_conn) -> None:
    """Verify tag creation generates unique slugs and rejects case-insensitive dupes."""
    tag = TagService.create_tag(
        empty_db_conn, "  Distributed Systems  ", description="Consensus and Raft"
    )
    assert tag["name"] == "Distributed Systems"
    assert tag["slug"] == "distributed-systems"
    assert tag["description"] == "Consensus and Raft"

    with pytest.raises(ValueError, match="already exists"):
        TagService.create_tag(empty_db_conn, "distributed systems")

    with pytest.raises(ValueError, match="cannot be empty"):
        TagService.create_tag(empty_db_conn, "   ")


def test_get_or_create_tags(empty_db_conn) -> None:
    """Verify batch tag resolution reuses existing tags and creates missing ones."""
    TagService.create_tag(empty_db_conn, "Python")
    resolved = TagService.get_or_create_tags(
        empty_db_conn, ["python", "SQLite", "  ", "Python", "Search"]
    )
    names = [t["name"] for t in resolved]
    assert names == ["Python", "SQLite", "Search"]
    assert len(TagService.list_tags(empty_db_conn, order_by="name")) == 3


def test_get_tag_with_posts_pagination(db_conn) -> None:
    """Verify retrieving a tag archive returns tag metadata and published posts."""
    result = TagService.get_tag_with_posts(db_conn, "python", page=1, page_size=10)
    assert result is not None
    tag, posts, total = result
    assert tag["slug"] == "python"
    assert total >= 1
    assert all(p["status"] == "published" for p in posts)

    assert TagService.get_tag_with_posts(db_conn, "non-existent-tag") is None


def test_generate_tag_cloud_scaling(empty_db_conn) -> None:
    """Verify tag cloud computes normalized weights and font sizes accurately."""
    # Empty cloud
    assert TagService.generate_tag_cloud(empty_db_conn) == []

    author = UserDAO.create(
        empty_db_conn, "author1", "a1@example.com", "pw", "Author One"
    )
    t_high = TagService.create_tag(empty_db_conn, "High")
    t_mid = TagService.create_tag(empty_db_conn, "Mid")
    t_low = TagService.create_tag(empty_db_conn, "Low")
    TagService.create_tag(empty_db_conn, "Unused")

    # 3 posts with High, 2 with Mid, 1 with Low, 0 with Unused
    PostDAO.create(
        empty_db_conn,
        author["id"],
        "P1",
        "Body 1",
        status="published",
        tag_ids=[t_high["id"], t_mid["id"], t_low["id"]],
    )
    PostDAO.create(
        empty_db_conn,
        author["id"],
        "P2",
        "Body 2",
        status="published",
        tag_ids=[t_high["id"], t_mid["id"]],
    )
    PostDAO.create(
        empty_db_conn,
        author["id"],
        "P3",
        "Body 3",
        status="published",
        tag_ids=[t_high["id"]],
    )
    TagDAO.recalculate_post_counts(empty_db_conn)

    cloud = TagService.generate_tag_cloud(
        empty_db_conn, min_size=1.0, max_size=2.0, include_empty=False
    )
    by_name = {t["name"]: t for t in cloud}
    assert "Unused" not in by_name
    assert by_name["High"]["weight"] == 1.0
    assert by_name["High"]["font_size"] == 2.0
    assert by_name["Mid"]["weight"] == 0.5
    assert by_name["Mid"]["font_size"] == 1.5
    assert by_name["Low"]["weight"] == 0.0
    assert by_name["Low"]["font_size"] == 1.0

    cloud_with_empty = TagService.generate_tag_cloud(empty_db_conn, include_empty=True)
    assert any(t["name"] == "Unused" for t in cloud_with_empty)


def test_jaccard_similarity_and_related_posts(empty_db_conn) -> None:
    """Verify Jaccard similarity coefficient and related post ranking."""
    assert TagService.jaccard_similarity(set(), set()) == 0.0
    assert TagService.jaccard_similarity({1, 2}, {3, 4}) == 0.0
    assert TagService.jaccard_similarity({1, 2}, {1, 2}) == 1.0
    assert TagService.jaccard_similarity({1, 2, 3}, {2, 3, 4}) == 0.5

    author = UserDAO.create(
        empty_db_conn, "author2", "a2@example.com", "pw", "Author Two"
    )
    t1 = TagService.create_tag(empty_db_conn, "Python")
    t2 = TagService.create_tag(empty_db_conn, "SQLite")
    t3 = TagService.create_tag(empty_db_conn, "Search")
    t4 = TagService.create_tag(empty_db_conn, "Frontend")

    target = PostDAO.create(
        empty_db_conn,
        author["id"],
        "Target Post",
        "Target",
        status="published",
        tag_ids=[t1["id"], t2["id"], t3["id"]],
    )
    # 2/3 = 0.6667 Jaccard
    best_match = PostDAO.create(
        empty_db_conn,
        author["id"],
        "Best Match",
        "Best",
        status="published",
        tag_ids=[t1["id"], t2["id"]],
    )
    # 1/4 = 0.25 Jaccard
    weak_match = PostDAO.create(
        empty_db_conn,
        author["id"],
        "Weak Match",
        "Weak",
        status="published",
        tag_ids=[t1["id"], t4["id"]],
    )
    # 0 overlap
    PostDAO.create(
        empty_db_conn,
        author["id"],
        "Unrelated",
        "None",
        status="published",
        tag_ids=[t4["id"]],
    )
    # Draft should be excluded even with full overlap
    PostDAO.create(
        empty_db_conn,
        author["id"],
        "Draft Match",
        "Draft",
        status="draft",
        tag_ids=[t1["id"], t2["id"], t3["id"]],
    )

    related = TagService.find_related_posts(empty_db_conn, target["id"], limit=4)
    assert [p["id"] for p in related] == [best_match["id"], weak_match["id"]]
    assert related[0]["similarity_score"] == round(2 / 3, 4)
    assert related[1]["similarity_score"] == 0.25
