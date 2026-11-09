"""Integration tests for GET and POST /oauth/userinfo endpoint."""

from app.db.connection import get_db
from app.models.token_model import TokenModel
from app.models.user_model import UserModel
from app.services.token_service import TokenService


def test_userinfo_success_full_claims(client, app, seeded_db):
    """Verify UserInfo returns sub, name, and email for openid profile email scopes."""
    with app.app_context():
        conn = get_db()
        rsa = app.extensions["rsa_manager"]
        issuer = app.config.get("ISSUER", "http://127.0.0.1:5000")
        user = UserModel.get_by_email(conn, "developer@pulseauth.dev")

        bundle = TokenService.issue_tokens(
            conn=conn,
            rsa_manager=rsa,
            issuer=issuer,
            client_id="pulse-web-app",
            scope="openid profile email",
            user=user,
        )
        token = bundle["access_token"]

    headers = {"Authorization": f"Bearer {token}"}
    resp = client.get("/oauth/userinfo", headers=headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["sub"] == str(user["id"])
    assert data["name"] == user["full_name"]
    assert data["email"] == user["email"]
    assert data["email_verified"] is True
    assert data["preferred_username"] == "developer"
    assert resp.headers["Cache-Control"] == "no-store"

    # POST method is also supported
    post_resp = client.post("/oauth/userinfo", headers=headers)
    assert post_resp.status_code == 200
    assert post_resp.get_json()["sub"] == str(user["id"])


def test_userinfo_minimal_openid_claims(client, app, seeded_db):
    """Verify UserInfo returns only sub when profile and email are not granted."""
    with app.app_context():
        conn = get_db()
        rsa = app.extensions["rsa_manager"]
        issuer = app.config.get("ISSUER", "http://127.0.0.1:5000")
        user = UserModel.get_by_email(conn, "developer@pulseauth.dev")

        bundle = TokenService.issue_tokens(
            conn=conn,
            rsa_manager=rsa,
            issuer=issuer,
            client_id="pulse-web-app",
            scope="openid",
            user=user,
        )
        token = bundle["access_token"]

    headers = {"Authorization": f"Bearer {token}"}
    resp = client.get("/oauth/userinfo", headers=headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["sub"] == str(user["id"])
    assert "email" not in data
    assert "name" not in data


def test_userinfo_missing_or_malformed_auth_header(client):
    """Verify missing and non-Bearer headers return 401 invalid_token."""
    # Missing header
    resp1 = client.get("/oauth/userinfo")
    assert resp1.status_code == 401
    assert resp1.get_json()["error"] == "invalid_token"

    # Not Bearer
    resp2 = client.get("/oauth/userinfo", headers={"Authorization": "Basic 123456"})
    assert resp2.status_code == 401
    assert resp2.get_json()["error"] == "invalid_token"

    # Empty Bearer
    resp3 = client.get("/oauth/userinfo", headers={"Authorization": "Bearer "})
    assert resp3.status_code == 401
    assert resp3.get_json()["error"] == "invalid_token"


def test_userinfo_invalid_and_revoked_tokens(client, app, seeded_db):
    """Verify tampered and revoked tokens return 401 invalid_token."""
    with app.app_context():
        conn = get_db()
        rsa = app.extensions["rsa_manager"]
        issuer = app.config.get("ISSUER", "http://127.0.0.1:5000")
        user = UserModel.get_by_email(conn, "developer@pulseauth.dev")

        bundle = TokenService.issue_tokens(
            conn=conn,
            rsa_manager=rsa,
            issuer=issuer,
            client_id="pulse-web-app",
            scope="openid",
            user=user,
        )
        token = bundle["access_token"]

    # Tampered token
    tampered = token[:-4] + "ZZZZ"
    resp_tamp = client.get(
        "/oauth/userinfo", headers={"Authorization": f"Bearer {tampered}"}
    )
    assert resp_tamp.status_code == 401
    assert resp_tamp.get_json()["error"] == "invalid_token"

    # Revoked token
    with app.app_context():
        TokenModel.revoke(get_db(), token)

    resp_rev = client.get(
        "/oauth/userinfo", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp_rev.status_code == 401
    assert "revoked" in resp_rev.get_json()["error_description"]


def test_userinfo_insufficient_scope(client, app, seeded_db):
    """Verify access token without openid scope returns 403 insufficient_scope."""
    with app.app_context():
        conn = get_db()
        rsa = app.extensions["rsa_manager"]
        issuer = app.config.get("ISSUER", "http://127.0.0.1:5000")
        user = UserModel.get_by_email(conn, "developer@pulseauth.dev")

        bundle = TokenService.issue_tokens(
            conn=conn,
            rsa_manager=rsa,
            issuer=issuer,
            client_id="pulse-web-app",
            scope="read:documents write:documents",
            user=user,
        )
        token = bundle["access_token"]

    headers = {"Authorization": f"Bearer {token}"}
    resp = client.get("/oauth/userinfo", headers=headers)
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "insufficient_scope"


def test_userinfo_m2m_service_token_forbidden(client, app, seeded_db):
    """Verify machine-to-machine tokens without user_id return 403 forbidden."""
    with app.app_context():
        conn = get_db()
        rsa = app.extensions["rsa_manager"]
        issuer = app.config.get("ISSUER", "http://127.0.0.1:5000")

        # M2M token issued with openid scope but user=None
        bundle = TokenService.issue_tokens(
            conn=conn,
            rsa_manager=rsa,
            issuer=issuer,
            client_id="pulse-m2m-service",
            scope="openid",
            user=None,
        )
        token = bundle["access_token"]

    headers = {"Authorization": f"Bearer {token}"}
    resp = client.get("/oauth/userinfo", headers=headers)
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "forbidden"
