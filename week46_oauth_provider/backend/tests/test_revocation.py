"""Tests for RFC 7009 OAuth 2.0 Token Revocation."""

import base64

from app.db.connection import get_db
from app.models.token_model import TokenModel
from app.models.user_model import UserModel
from app.services.token_service import TokenService


def test_revoke_access_token_confidential_client_success(client, app, seeded_db):
    """Verify revoking an access token by confidential client."""
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

    raw_token = tokens["access_token"]

    # Revoke with form credentials
    resp = client.post(
        "/oauth/revoke",
        data={
            "token": raw_token,
            "token_type_hint": "access_token",
            "client_id": "pulse-web-app",
            "client_secret": "pulse_web_secret_2026",
        },
    )
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "revoked"

    # Confirm token is revoked in database
    with app.app_context():
        conn = get_db()
        valid, _, err = TokenModel.is_valid(conn, raw_token)
        assert valid is False
        assert "revoked" in err


def test_revoke_refresh_token_revokes_entire_family(client, app, seeded_db):
    """Verify revoking a refresh token revokes all associated tokens in family."""
    with app.app_context():
        conn = get_db()
        rsa = app.extensions["rsa_manager"]
        user = UserModel.get_by_id(conn, 1)
        tokens = TokenService.issue_tokens(
            conn=conn,
            rsa_manager=rsa,
            issuer="http://127.0.0.1:5000",
            client_id="pulse-web-app",
            scope="openid profile offline_access",
            user=user,
            include_refresh=True,
        )

    rt = tokens["refresh_token"]
    at = tokens["access_token"]

    # Revoke using Basic Auth
    creds = base64.b64encode(b"pulse-web-app:pulse_web_secret_2026").decode()
    resp = client.post(
        "/oauth/revoke",
        data={"token": rt, "token_type_hint": "refresh_token"},
        headers={"Authorization": f"Basic {creds}"},
    )
    assert resp.status_code == 200

    # Verify both refresh token and access token are now revoked
    with app.app_context():
        conn = get_db()
        valid_rt, _, _ = TokenModel.is_valid(conn, rt)
        valid_at, _, _ = TokenModel.is_valid(conn, at)
        assert valid_rt is False
        assert valid_at is False


def test_revoke_public_client_success(client, app, seeded_db):
    """Verify public client can revoke its own tokens."""
    with app.app_context():
        conn = get_db()
        rsa = app.extensions["rsa_manager"]
        user = UserModel.get_by_id(conn, 1)
        tokens = TokenService.issue_tokens(
            conn=conn,
            rsa_manager=rsa,
            issuer="http://127.0.0.1:5000",
            client_id="pulse-mobile-app",
            scope="openid profile",
            user=user,
        )

    resp = client.post(
        "/oauth/revoke",
        data={"token": tokens["access_token"], "client_id": "pulse-mobile-app"},
    )
    assert resp.status_code == 200


def test_revoke_invalid_or_nonexistent_token_returns_200(client, app, seeded_db):
    """RFC 7009 Section 2.2: returns 200 for invalid/nonexistent tokens."""
    resp = client.post(
        "/oauth/revoke",
        data={
            "token": "completely_bogus_token_12345",
            "client_id": "pulse-mobile-app",
        },
    )
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "revoked"


def test_revoke_different_client_token_ignored(client, app, seeded_db):
    """RFC 7009 Section 2.1: token issued to another client is not revoked."""
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

    # pulse-mobile-app attempts to revoke pulse-web-app's token
    resp = client.post(
        "/oauth/revoke",
        data={"token": at, "client_id": "pulse-mobile-app"},
    )
    assert resp.status_code == 200

    # Token must STILL be valid for pulse-web-app
    with app.app_context():
        conn = get_db()
        valid, _, _ = TokenModel.is_valid(conn, at)
        assert valid is True


def test_revoke_missing_token_parameter(client, app, seeded_db):
    """Verify missing token parameter returns 400 invalid_request."""
    resp = client.post(
        "/oauth/revoke",
        data={"client_id": "pulse-mobile-app"},
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "invalid_request"


def test_revoke_unauthenticated_client_rejected(client, app, seeded_db):
    """Verify invalid client credentials return 401 invalid_client."""
    resp = client.post(
        "/oauth/revoke",
        data={
            "token": "some_token",
            "client_id": "pulse-web-app",
            "client_secret": "wrong_secret",
        },
    )
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "invalid_client"
