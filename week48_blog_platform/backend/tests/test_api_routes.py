"""End-to-end integration tests for PulsePress REST API Gateway routes."""

from typing import Dict


def _auth_header(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _login(client, identifier: str, password: str) -> str:
    res = client.post(
        "/api/auth/login",
        json={"username": identifier, "password": password},
    )
    assert res.status_code == 200
    return res.get_json()["data"]["token"]


def test_auth_register_login_and_me(client) -> None:
    """Verify registration, duplicate rejection, login, and JWT Bearer /me."""
    reg_res = client.post(
        "/api/auth/register",
        json={
            "username": "newauthor",
            "email": "newauthor@example.com",
            "password": "StrongPassword123!",
            "display_name": "New Author",
        },
    )
    assert reg_res.status_code == 201
    reg_data = reg_res.get_json()["data"]
    assert reg_data["user"]["username"] == "newauthor"
    assert reg_data["user"]["role"] == "author"
    assert "password_hash" not in reg_data["user"]
    token = reg_data["token"]

    # Duplicate username -> 409
    dup_res = client.post(
        "/api/auth/register",
        json={
            "username": "newauthor",
            "email": "other@example.com",
            "password": "StrongPassword123!",
        },
    )
    assert dup_res.status_code == 409

    # /me with valid token -> 200
    me_res = client.get("/api/auth/me", headers=_auth_header(token))
    assert me_res.status_code == 200
    assert me_res.get_json()["data"]["user"]["username"] == "newauthor"

    # /me without token -> 401
    unauth = client.get("/api/auth/me")
    assert unauth.status_code == 401

    # /me with tampered token -> 401
    bad_tok = client.get("/api/auth/me", headers=_auth_header(token + "tamper"))
    assert bad_tok.status_code == 401

    # Login with seeded admin
    admin_token = _login(client, "admin", "AdminPassword123!")
    admin_me = client.get("/api/auth/me", headers=_auth_header(admin_token))
    assert admin_me.status_code == 200
    assert admin_me.get_json()["data"]["user"]["role"] == "admin"

    # Bad password -> 401
    bad_login = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "WrongPassword"},
    )
    assert bad_login.status_code == 401


def test_post_crud_publish_and_rbac(client) -> None:
    """Verify full post lifecycle: create draft, publish, read, update, and delete."""
    # Unauthenticated create -> 401
    no_auth = client.post(
        "/api/posts",
        json={"title": "Blocked", "body_markdown": "Body"},
    )
    assert no_auth.status_code == 401

    # Register author A and author B
    res_a = client.post(
        "/api/auth/register",
        json={
            "username": "author_a",
            "email": "a@example.com",
            "password": "Password123!",
        },
    )
    token_a = res_a.get_json()["data"]["token"]

    res_b = client.post(
        "/api/auth/register",
        json={
            "username": "author_b",
            "email": "b@example.com",
            "password": "Password123!",
        },
    )
    token_b = res_b.get_json()["data"]["token"]

    # Author A creates a draft post
    create_res = client.post(
        "/api/posts",
        headers=_auth_header(token_a),
        json={
            "title": "Deep Dive into SQLite WAL Mode",
            "body_markdown": (
                "# Overview\n\nSQLite WAL improves concurrency.\n\n"
                "```sql\nPRAGMA journal_mode = WAL;\n```"
            ),
            "tags": ["SQLite", "Databases"],
            "status": "draft",
        },
    )
    assert create_res.status_code == 201
    post = create_res.get_json()["data"]["post"]
    slug = post["slug"]
    assert post["status"] == "draft"
    assert "<h1" in post["body_html"]
    assert len(post["toc"]) == 1

    # Public reader cannot see draft -> 404
    assert client.get(f"/api/posts/{slug}").status_code == 404

    # Author B cannot update or delete Author A's post -> 403
    assert (
        client.put(
            f"/api/posts/{slug}",
            headers=_auth_header(token_b),
            json={"title": "Hijacked"},
        ).status_code
        == 403
    )
    assert (
        client.delete(
            f"/api/posts/{slug}",
            headers=_auth_header(token_b),
        ).status_code
        == 403
    )

    # Author A publishes the post
    pub_res = client.post(
        f"/api/posts/{slug}/publish",
        headers=_auth_header(token_a),
    )
    assert pub_res.status_code == 200
    assert pub_res.get_json()["data"]["post"]["status"] == "published"

    # Public reader can now fetch published post (records view & returns related)
    read_res = client.get(
        f"/api/posts/{slug}",
        headers={"X-Visitor-Hash": "visitor-abc-123"},
    )
    assert read_res.status_code == 200
    read_post = read_res.get_json()["data"]["post"]
    assert read_post["view_count"] >= 1
    assert "related_posts" in read_post

    # Author A updates content
    upd_res = client.put(
        f"/api/posts/{slug}",
        headers=_auth_header(token_a),
        json={
            "title": "Deep Dive into SQLite WAL Mode (Updated)",
            "body_markdown": "# Updated\n\nNew WAL benchmark results.",
            "tags": ["SQLite", "Performance"],
        },
    )
    assert upd_res.status_code == 200
    assert upd_res.get_json()["data"]["post"]["title"].endswith("(Updated)")

    # List posts with pagination
    list_res = client.get("/api/posts?page=1&page_size=5")
    assert list_res.status_code == 200
    assert list_res.get_json()["data"]["total"] >= 1

    # Author A deletes post
    del_res = client.delete(
        f"/api/posts/{slug}",
        headers=_auth_header(token_a),
    )
    assert del_res.status_code == 200
    assert client.get(f"/api/posts/{slug}").status_code == 404


def test_search_and_tag_endpoints(client) -> None:
    """Verify BM25 search, tag filtering, autocomplete, and tag archive endpoints."""
    # Search seeded content
    search_res = client.get("/api/search?q=sqlite")
    assert search_res.status_code == 200
    s_data = search_res.get_json()["data"]
    assert s_data["total"] >= 1
    assert len(s_data["results"]) >= 1

    # Search with tag filter
    filtered_res = client.get("/api/search?q=sqlite&tags=python")
    assert filtered_res.status_code == 200

    # Autocomplete
    auto_res = client.get("/api/search/autocomplete?q=sql")
    assert auto_res.status_code == 200
    assert "suggestions" in auto_res.get_json()["data"]

    # Tag cloud
    tags_res = client.get("/api/tags")
    assert tags_res.status_code == 200
    tags = tags_res.get_json()["data"]["tags"]
    assert len(tags) >= 1
    first_slug = tags[0]["slug"]

    # Posts by tag
    tag_posts_res = client.get(f"/api/tags/{first_slug}/posts")
    assert tag_posts_res.status_code == 200
    assert tag_posts_res.get_json()["data"]["tag"]["slug"] == first_slug

    # Non-existent tag -> 404
    assert client.get("/api/tags/does-not-exist/posts").status_code == 404


def test_comments_rate_limit_and_admin_moderation(client) -> None:
    """Verify comment submission, threaded retrieval, 429 rate limit, and moderation."""
    posts_res = client.get("/api/posts")
    slug = posts_res.get_json()["data"]["posts"][0]["slug"]

    # Submit a comment (starts as pending)
    sub_res = client.post(
        f"/api/posts/{slug}/comments",
        json={
            "author_name": "Curious Reader",
            "author_email": "reader@example.com",
            "body": "Great technical breakdown!",
        },
        headers={"X-Forwarded-For": "198.51.100.10"},
    )
    assert sub_res.status_code == 201
    comment_id = sub_res.get_json()["data"]["comment"]["id"]

    # Register normal author (not admin) -> moderation forbidden (403)
    reg_res = client.post(
        "/api/auth/register",
        json={
            "username": "regular_author",
            "email": "reg@example.com",
            "password": "Password123!",
        },
    )
    author_token = reg_res.get_json()["data"]["token"]
    assert (
        client.put(
            f"/api/comments/{comment_id}/moderate",
            headers=_auth_header(author_token),
            json={"status": "approved"},
        ).status_code
        == 403
    )

    # Admin checks queue and approves comment
    admin_token = _login(client, "admin", "AdminPassword123!")
    queue_res = client.get(
        "/api/comments/queue?status=pending",
        headers=_auth_header(admin_token),
    )
    assert queue_res.status_code == 200
    assert any(c["id"] == comment_id for c in queue_res.get_json()["data"]["comments"])

    mod_res = client.put(
        f"/api/comments/{comment_id}/moderate",
        headers=_auth_header(admin_token),
        json={"status": "approved"},
    )
    assert mod_res.status_code == 200
    assert mod_res.get_json()["data"]["comment"]["status"] == "approved"

    # Approved comment now appears in public threaded tree
    tree_res = client.get(f"/api/posts/{slug}/comments")
    assert tree_res.status_code == 200
    comments = tree_res.get_json()["data"]["comments"]
    assert any(c["id"] == comment_id for c in comments)

    # Exhaust 5-comment rate limit from same IP -> 6th returns 429
    for idx in range(4):
        r = client.post(
            f"/api/posts/{slug}/comments",
            json={
                "author_name": f"Burst {idx}",
                "author_email": f"b{idx}@example.com",
                "body": f"Burst comment {idx}",
            },
            headers={"X-Forwarded-For": "198.51.100.10"},
        )
        assert r.status_code == 201

    limited = client.post(
        f"/api/posts/{slug}/comments",
        json={
            "author_name": "Too Fast",
            "author_email": "fast@example.com",
            "body": "Should be rate-limited",
        },
        headers={"X-Forwarded-For": "198.51.100.10"},
    )
    assert limited.status_code == 429


def test_analytics_endpoints(client) -> None:
    """Verify post analytics metrics and top posts endpoints."""
    posts_res = client.get("/api/posts")
    first_post = posts_res.get_json()["data"]["posts"][0]
    post_id = first_post["id"]
    slug = first_post["slug"]

    # Trigger 2 distinct visitor views
    client.get(f"/api/posts/{slug}", headers={"X-Visitor-Hash": "v1"})
    client.get(f"/api/posts/{slug}", headers={"X-Visitor-Hash": "v2"})

    stats_res = client.get(f"/api/analytics/posts/{post_id}")
    assert stats_res.status_code == 200
    stats = stats_res.get_json()["data"]
    assert stats["post_id"] == post_id
    assert stats["view_count"] >= 2
    assert stats["unique_visitors"] >= 2

    assert client.get("/api/analytics/posts/999999").status_code == 404

    top_res = client.get("/api/analytics/top?limit=5")
    assert top_res.status_code == 200
    assert len(top_res.get_json()["data"]["posts"]) >= 1
