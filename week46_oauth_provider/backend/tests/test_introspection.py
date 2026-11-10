"""Tests for RFC 7662 OAuth 2.0 Token Introspection."""

import base64
from datetime import datetime, timedelta, timezone

from app.db.connection import get_db
from app.models.token_model import TokenModel
from app.models.user_model import UserModel
from app.services.token_service import TokenService


def test_introspect_active_access_token_success(client, app, seeded_db):
    """Verify introspecting an active RS256 JWT access token."""
    with app.app_context():
        conn = get_db()
        rsa = app.extensions["rsa_manager"]
        user = UserModel.get_by_id(conn, 1)
        tokens = TokenService.issue_tokens(
            conn=conn,
            rsa_manager=rsa,
            issuer="http://127.0.0.1:5000",
            client_id="pulse-web-app",
            scope="openid profile",
            user=user,
        )

    at = tokens["access_token"]

    creds = base64.b64encode(b"pulse-web-app:pulse_web_secret_2026").decode()
    resp = client.post(
        "/oauth/introspect",
        data={"token": at, "token_type_hint": "access_token"},
        headers={"Authorization": f"Basic {creds}"},
    )
    assert resp.status_code == 200
    data = resp.get_json()

    assert data["active"] is True
    assert data["scope"] == "openid profile"
    assert data["client_id"] == "pulse-web-app"
    assert data["sub"] == "1"
    assert data["token_type"] == "Bearer"
    assert "exp" in data
    assert "iat" in data
    assert data["iss"] == "http://127.0.0.1:5000"
    assert resp.headers["Cache-Control"] == "no-store"


def test_introspect_active_refresh_token(client, app, seeded_db):
    """Verify introspecting an active opaque refresh token."""
    with app.app_context():
        conn = get_db()
        rsa = app.extensions["rsa_manager"]
        user = UserModel.get_by_id(conn, 1)
        tokens = TokenService.issue_tokens(
            conn=conn,
            rsa_manager=rsa,
            issuer="http://127.0.0.1:5000",
            client_id="pulse-web-app",
            scope="openid offline_access",
            user=user,
            include_refresh=True,
        )

    rt = tokens["refresh_token"]

    resp = client.post(
        "/oauth/introspect",
        data={
            "token": rt,
            "client_id": "pulse-web-app",
            "client_secret": "pulse_web_secret_2026",
        },
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["active"] is True
    assert data["token_type_hint"] == "refresh_token"


def test_introspect_revoked_token_returns_active_false(client, app, seeded_db):
    """Verify revoked token returns active=false."""
    with app.app_context():
        conn = get_db()
        rsa = app.extensions["rsa_manager"]
        user = UserModel.get_by_id(conn, 1)
        tokens = TokenService.issue_tokens(
            conn=conn,
            rsa_manager=rsa,
            issuer="http://127.0.0.1:5000",
            client_id="pulse-web-app",
            scope="openid",
            user=user,
        )
        at = tokens["access_token"]
        TokenModel.revoke(conn, at)

    resp = client.post(
        "/oauth/introspect",
        data={
            "token": at,
            "client_id": "pulse-web-app",
            "client_secret": "pulse_web_secret_2026",
        },
    )
    assert resp.status_code == 200
    assert resp.get_json() == {"active": False}


def test_introspect_expired_token_returns_active_false(client, app, seeded_db):
    """Verify expired token returns active=false."""
    with app.app_context():
        conn = get_db()
        past = datetime.now(timezone.utc) - timedelta(hours=2)
        TokenModel.create(
            conn=conn,
            token_type="access_token",
            raw_token="expired_raw_jwt_or_string",
            client_id="pulse-web-app",
            scope="openid",
            expires_at=past,
            user_id=1,
        )

    resp = client.post(
        "/oauth/introspect",
        data={
            "token": "expired_raw_jwt_or_string",
            "client_id": "pulse-web-app",
            "client_secret": "pulse_web_secret_2026",
        },
    )
    assert resp.status_code == 200
    assert resp.get_json() == {"active": False}


def test_introspect_nonexistent_token_returns_active_false(client, app, seeded_db):
    """Verify nonexistent token returns active=false."""
    resp = client.post(
        "/oauth/introspect",
        data={
            "token": "random_unregistered_token_value",
            "client_id": "pulse-web-app",
            "client_secret": "pulse_web_secret_2026",
        },
    )
    assert resp.status_code == 200
    assert resp.get_json() == {"active": False}


def test_introspect_resource_server_cross_client(client, app, seeded_db):
    """
    Test RFC 7662 cross-client resource server token validation.

    Resource server pulse-m2m-service validates a token issued to pulse-web-app.
    """
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

    at = tokens["access_token"]

    # Resource server authenticates with its own credentials
    resp = client.post(
        "/oauth/introspect",
        json={"token": at},
        headers={
            "Authorization": "Basic "
            + base64.b64encode(b"pulse-m2m-service:pulse_m2m_secret_2026").decode()
        },
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["active"] is True
    assert data["client_id"] == "pulse-web-app"
    assert data["scope"] == "read:documents write:documents"


def test_introspect_missing_token_param(client, app, seeded_db):
    """Verify missing token parameter returns 400 invalid_request."""
    resp = client.post(
        "/oauth/introspect",
        data={
            "client_id": "pulse-web-app",
            "client_secret": "pulse_web_secret_2026",
        },
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "invalid_request"


def test_introspect_unauthenticated_or_public_client_rejected(client, app, seeded_db):
    """Verify unauthenticated client or public client is rejected."""
    # Public client cannot introspect
    resp_pub = client.post(
        "/oauth/introspect",
        data={"token": "some_token", "client_id": "pulse-mobile-app"},
    )
    assert resp_pub.status_code == 400
    assert resp_pub.get_json()["error"] == "unauthorized_client"

    # Confidential client with bad secret
    resp_bad = client.post(
        "/oauth/introspect",
        data={
            "token": "some_token",
            "client_id": "pulse-web-app",
            "client_secret": "bad_secret",
        },
    )
    assert resp_bad.status_code == 401
    assert resp_bad.get_json()["error"] == "invalid_client"
