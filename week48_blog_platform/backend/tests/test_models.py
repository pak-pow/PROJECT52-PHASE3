"""Tests for all Data Access Objects (User, Post, Tag, Comment, Search, Analytics)."""

from app.models.analytics import AnalyticsDAO
from app.models.comment import CommentDAO
from app.models.post import PostDAO
from app.models.search_entry import SearchIndexDAO
from app.models.tag import TagDAO
from app.models.user import UserDAO


def test_user_dao_full_lifecycle(empty_db_conn):
    """Test full CRUD lifecycle for UserDAO."""
    user = UserDAO.create(
        empty_db_conn,
        username="john_doe",
        email="john@example.com",
        password="SecurePassword123!",
        display_name="John Doe",
        bio="Full stack developer",
    )
    assert user["id"] is not None
    assert user["username"] == "john_doe"

    # Fetch by ID, username, email
    assert UserDAO.get_by_id(empty_db_conn, user["id"])["email"] == "john@example.com"
    assert UserDAO.get_by_username(empty_db_conn, "john_doe") is not None
    assert UserDAO.get_by_email(empty_db_conn, "john@example.com") is not None
    assert UserDAO.get_by_username(empty_db_conn, "non_existent") is None
    assert UserDAO.get_by_email(empty_db_conn, "none@example.com") is None
    assert UserDAO.get_by_id(empty_db_conn, 9999) is None

    # Password verification
    assert UserDAO.verify_password(user, "SecurePassword123!") is True
    assert UserDAO.verify_password(user, "WrongPassword") is False

    # Update
    updated = UserDAO.update(
        empty_db_conn, user["id"], display_name="Johnny Doe", role="admin"
    )
    assert updated["display_name"] == "Johnny Doe"
    assert updated["role"] == "admin"

    # List all
    all_users = UserDAO.list_all(empty_db_conn)
    assert len(all_users) == 1

    # Delete
    assert UserDAO.delete(empty_db_conn, user["id"]) is True
    assert UserDAO.get_by_id(empty_db_conn, user["id"]) is None


def test_tag_dao_crud_and_association(db_conn):
    """Test TagDAO operations, post tagging, and count recalculation."""
    new_tag = TagDAO.create(
        db_conn, name="Distributed Systems", description="Decentralized computing"
    )
    assert new_tag["slug"] == "distributed-systems"

    # Retrieve by slug
    fetched = TagDAO.get_by_slug(db_conn, "distributed-systems")
    assert fetched["id"] == new_tag["id"]

    # Tag ordering
    by_name = TagDAO.list_all(db_conn, order_by="name")
    assert len(by_name) >= 7
    by_count = TagDAO.list_all(db_conn, order_by="count")
    assert len(by_count) >= 7

    # Update tag
    updated = TagDAO.update(db_conn, new_tag["id"], name="Distributed Computing")
    assert updated["name"] == "Distributed Computing"

    # Attach to post 1
    TagDAO.set_tags_for_post(db_conn, 1, [new_tag["id"]])
    post_tags = TagDAO.get_tags_for_post(db_conn, 1)
    assert any(t["id"] == new_tag["id"] for t in post_tags)

    # Delete tag
    assert TagDAO.delete(db_conn, new_tag["id"]) is True
    assert TagDAO.get_by_id(db_conn, new_tag["id"]) is None


def test_post_dao_crud_and_queries(db_conn):
    """Test PostDAO creation, updates, filtering, and deletion."""
    post = PostDAO.create(
        db_conn,
        author_id=1,
        title="Modern Concurrency in Python",
        body_markdown="# Concurrency\nUsing asyncio and threads.",
        excerpt="Quick guide to Python concurrency.",
        status="draft",
        tag_ids=[1, 2],
    )
    assert post["slug"] == "modern-concurrency-in-python"
    assert post["status"] == "draft"
    assert len(post["tags"]) == 2

    # Fetch by slug
    by_slug = PostDAO.get_by_slug(db_conn, "modern-concurrency-in-python")
    assert by_slug["id"] == post["id"]

    # Non-existent slug and id
    assert PostDAO.get_by_slug(db_conn, "non-existent-slug") is None
    assert PostDAO.get_by_id(db_conn, 99999) is None

    # Publish post
    published = PostDAO.publish(db_conn, post["id"])
    assert published["status"] == "published"
    assert published["published_at"] is not None

    # List posts with filters
    posts, total = PostDAO.list_posts(db_conn, status="published", page=1, page_size=2)
    assert len(posts) == 2
    assert total >= 4

    # List with tag slug filter
    py_posts, py_total = PostDAO.list_posts(db_conn, tag_slug="python")
    assert py_total >= 3

    # List with author filter
    author_posts, author_total = PostDAO.list_posts(db_conn, author_id=1)
    assert author_total >= 1

    # Delete post
    assert PostDAO.delete(db_conn, post["id"]) is True
    assert PostDAO.get_by_id(db_conn, post["id"]) is None


def test_comment_dao_threading_and_moderation(db_conn):
    """Test CommentDAO hierarchical tree assembly, moderation, and rate limits."""
    # Create top-level comment
    c1 = CommentDAO.create(
        db_conn,
        post_id=1,
        author_name="David Kim",
        author_email="david@example.com",
        author_ip_hash="test_ip_hash_1",
        body="Great article!",
        status="approved",
    )
    # Create reply
    c2 = CommentDAO.create(
        db_conn,
        post_id=1,
        parent_id=c1["id"],
        author_name="Sarah Chen",
        author_email="sarah@pulsepress.dev",
        author_ip_hash="test_ip_hash_2",
        body="Glad you found it useful David!",
        status="approved",
    )

    # Threaded tree structure
    tree = CommentDAO.get_threaded_tree(db_conn, 1, status="approved")
    # Verify c1 is root and c2 is child in replies
    matching_root = next((r for r in tree if r["id"] == c1["id"]), None)
    assert matching_root is not None
    assert any(reply["id"] == c2["id"] for reply in matching_root["replies"])

    # Update status
    updated = CommentDAO.update_status(db_conn, c1["id"], "flagged")
    assert updated["status"] == "flagged"

    # Rate limiting counter
    count = CommentDAO.count_recent_from_ip(db_conn, "test_ip_hash_1", minutes=10)
    assert count >= 1

    # Delete
    assert CommentDAO.delete(db_conn, c1["id"]) is True


def test_search_index_dao_operations(db_conn):
    """Test SearchIndexDAO indexing, term statistics, and autocomplete."""
    terms = {"python": 3, "concurrency": 2, "asyncio": 5}
    SearchIndexDAO.insert_terms(db_conn, 1, "body", terms, doc_length=100)

    # Verify retrieval
    post_terms = SearchIndexDAO.get_terms_for_post(db_conn, 1)
    assert len(post_terms) >= 3

    # Term matches
    matches = SearchIndexDAO.get_post_matches_for_term(db_conn, "concurrency")
    assert len(matches) == 1
    assert matches[0][0] == 1  # post_id
    assert matches[0][2] == 2  # tf

    # Autocomplete
    suggestions = SearchIndexDAO.autocomplete_terms(db_conn, "con", limit=5)
    assert "concurrency" in suggestions

    # Avg doc length and total indexed posts
    assert SearchIndexDAO.get_total_indexed_posts(db_conn) >= 1
    avg_len = SearchIndexDAO.get_avg_doc_length(db_conn, field="body")
    assert avg_len > 0.0

    # Purge
    deleted = SearchIndexDAO.delete_by_post(db_conn, 1)
    assert deleted >= 3


def test_analytics_dao_view_tracking(db_conn):
    """Test AnalyticsDAO page views recording and aggregation."""
    AnalyticsDAO.record_view(db_conn, 1, "visitor_hash_abc")
    AnalyticsDAO.record_view(db_conn, 1, "visitor_hash_abc")
    AnalyticsDAO.record_view(db_conn, 1, "visitor_hash_def")

    views = AnalyticsDAO.get_post_views(db_conn, 1)
    assert views == 3

    unique = AnalyticsDAO.get_post_unique_visitors(db_conn, 1)
    assert unique == 2

    top = AnalyticsDAO.get_top_posts_by_views(db_conn, limit=3)
    assert len(top) >= 1
    assert top[0]["id"] == 1
