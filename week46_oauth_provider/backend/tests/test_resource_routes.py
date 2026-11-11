"""Integration tests for protected demo resource server endpoints."""

from app.db.connection import get_db
from app.models.user_model import UserModel
from app.services.token_service import TokenService


def test_resource_profile_success(client, app, seeded_db):
    """Verify GET /api/v1/resource/profile with valid Bearer token."""
    with app.app_context():
        conn = get_db()
        rsa = app.extensions["rsa_manager"]
        user = UserModel.get_by_id(conn, 1)
        tokens = TokenService.issue_tokens(
            conn=conn,
            rsa_manager=rsa,
            issuer="http://127.0.0.1:5000",
            client_id="pulse-web-app",
            scope="openid profile email",
            user=user,
        )

    resp = client.get(
        "/api/v1/resource/profile",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "success"
    assert data["data"]["sub"] == "1"
    assert data["data"]["email"] == "developer@pulseauth.dev"
    assert data["data"]["full_name"] == "Alice Dev"
    assert data["data"]["client_id"] == "pulse-web-app"


def test_resource_profile_insufficient_scope(client, app, seeded_db):
    """Verify 403 Forbidden when token lacks profile or openid scopes."""
    with app.app_context():
        conn = get_db()
        rsa = app.extensions["rsa_manager"]
        user = UserModel.get_by_id(conn, 1)
        tokens = TokenService.issue_tokens(
            conn=conn,
            rsa_manager=rsa,
            issuer="http://127.0.0.1:5000",
            client_id="pulse-web-app",
            scope="read:documents",
            user=user,
        )

    resp = client.get(
        "/api/v1/resource/profile",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "insufficient_scope"


def test_resource_documents_get_and_post(client, app, seeded_db):
    """Verify read:documents and write:documents resource access."""
    with app.app_context():
        conn = get_db()
        rsa = app.extensions["rsa_manager"]
        user = UserModel.get_by_id(conn, 1)
        tokens = TokenService.issue_tokens(
            conn=conn,
            rsa_manager=rsa,
            issuer="http://127.0.0.1:5000",
            client_id="pulse-web-app",
            scope="read:documents write:documents",
            user=user,
        )

    token = tokens["access_token"]

    # 1. GET /api/v1/resource/documents
    resp_get = client.get(
        "/api/v1/resource/documents",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_get.status_code == 200
    get_data = resp_get.get_json()
    assert get_data["status"] == "success"
    assert get_data["count"] == 3
    assert len(get_data["data"]) == 3

    # 2. POST /api/v1/resource/documents
    doc_payload = {
        "title": "Quantum Resistance Migration Plan",
        "classification": "Top Secret",
    }
    resp_post = client.post(
        "/api/v1/resource/documents",
        json=doc_payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_post.status_code == 201
    post_data = resp_post.get_json()
    assert post_data["status"] == "success"
    assert post_data["data"]["title"] == "Quantum Resistance Migration Plan"
    assert post_data["data"]["classification"] == "Top Secret"
    assert post_data["data"]["owner"] == "1"


def test_resource_documents_missing_title(client, app, seeded_db):
    """Verify 400 Bad Request when creating document without title."""
    with app.app_context():
        conn = get_db()
        rsa = app.extensions["rsa_manager"]
        user = UserModel.get_by_id(conn, 1)
        tokens = TokenService.issue_tokens(
            conn=conn,
            rsa_manager=rsa,
            issuer="http://127.0.0.1:5000",
            client_id="pulse-web-app",
            scope="write:documents",
            user=user,
        )

    resp = client.post(
        "/api/v1/resource/documents",
        json={},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "invalid_request"


def test_resource_documents_write_unauthorized(client, app, seeded_db):
    """Verify 403 Forbidden when token has read:documents but lacks write:documents."""
    with app.app_context():
        conn = get_db()
        rsa = app.extensions["rsa_manager"]
        user = UserModel.get_by_id(conn, 1)
        tokens = TokenService.issue_tokens(
            conn=conn,
            rsa_manager=rsa,
            issuer="http://127.0.0.1:5000",
            client_id="pulse-web-app",
            scope="read:documents",
            user=user,
        )

    resp = client.post(
        "/api/v1/resource/documents",
        json={"title": "Unauthorized Document"},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "insufficient_scope"
