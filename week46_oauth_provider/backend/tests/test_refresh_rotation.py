"""Tests for refresh token rotation, lineage tracking, and reuse detection."""

from datetime import datetime, timedelta, timezone

from app.db.connection import get_db
from app.models.token_model import TokenModel
from app.models.user_model import UserModel
from app.services.token_service import TokenService


def test_refresh_rotation_confidential_client_success(client, app, seeded_db):
    """Verify refresh token rotation for confidential client with Basic auth."""
    with app.app_context():
        conn = get_db()
        rsa = app.extensions["rsa_manager"]
        user = UserModel.get_by_id(conn, 1)
        tokens = TokenService.issue_tokens(
            conn=conn,
            rsa_manager=rsa,
            issuer="http://127.0.0.1:5000",
            client_id="pulse-web-app",
            scope="openid profile email offline_access",
            user=user,
            include_refresh=True,
        )

    old_refresh_token = tokens["refresh_token"]

    payload = {
        "grant_type": "refresh_token",
        "refresh_token": old_refresh_token,
        "client_id": "pulse-web-app",
        "client_secret": "pulse_web_secret_2026",
    }
    resp = client.post("/oauth/token", data=payload)
    assert resp.status_code == 200
    data = resp.get_json()

    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "Bearer"
    assert data["refresh_token"] != old_refresh_token
    assert resp.headers["Cache-Control"] == "no-store"

    # Verify old refresh token is marked as revoked in database
    with app.app_context():
        conn = get_db()
        valid, rec, err = TokenModel.is_valid(conn, old_refresh_token)
        assert valid is False
        assert "revoked" in err

        # Verify new refresh token is active
        valid_new, rec_new, _ = TokenModel.is_valid(conn, data["refresh_token"])
        assert valid_new is True
        # Verify same family lineage
        assert rec["token_family_id"] == rec_new["token_family_id"]


def test_refresh_rotation_public_client_success(client, app, seeded_db):
    """Verify refresh token rotation for public PKCE client without secret."""
    with app.app_context():
        conn = get_db()
        rsa = app.extensions["rsa_manager"]
        user = UserModel.get_by_id(conn, 1)
        tokens = TokenService.issue_tokens(
            conn=conn,
            rsa_manager=rsa,
            issuer="http://127.0.0.1:5000",
            client_id="pulse-mobile-app",
            scope="openid profile offline_access",
            user=user,
            include_refresh=True,
        )

    payload = {
        "grant_type": "refresh_token",
        "refresh_token": tokens["refresh_token"],
        "client_id": "pulse-mobile-app",
    }
    resp = client.post("/oauth/token", data=payload)
    assert resp.status_code == 200
    data = resp.get_json()
    assert "access_token" in data
    assert "refresh_token" in data


def test_refresh_reuse_detection_triggers_family_revocation(client, app, seeded_db):
    """
    Test RFC 6749 Section 6 reuse defense.

    Submitting a previously rotated refresh token indicates token theft.
    PulseAuth must detect the reuse and immediately revoke all tokens in the family.
    """
    with app.app_context():
        conn = get_db()
        rsa = app.extensions["rsa_manager"]
        user = UserModel.get_by_id(conn, 1)
        # Legitimate initial issuance (RT1)
        tokens1 = TokenService.issue_tokens(
            conn=conn,
            rsa_manager=rsa,
            issuer="http://127.0.0.1:5000",
            client_id="pulse-web-app",
            scope="openid profile offline_access",
            user=user,
            include_refresh=True,
        )

    rt1 = tokens1["refresh_token"]

    # Step 1: Legitimate client rotates RT1 -> gets RT2
    resp1 = client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": rt1,
            "client_id": "pulse-web-app",
            "client_secret": "pulse_web_secret_2026",
        },
    )
    assert resp1.status_code == 200
    rt2 = resp1.get_json()["refresh_token"]

    # Step 2: Attacker replays RT1 (which is already rotated / revoked)
    resp_attack = client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": rt1,
            "client_id": "pulse-web-app",
            "client_secret": "pulse_web_secret_2026",
        },
    )
    assert resp_attack.status_code == 400
    err_data = resp_attack.get_json()
    assert err_data["error"] == "invalid_grant"
    assert "revoked or reused" in err_data["error_description"]

    # Step 3: Verify that RT2 was revoked as part of the family invalidation
    with app.app_context():
        conn = get_db()
        valid, _, err = TokenModel.is_valid(conn, rt2)
        assert valid is False
        assert "revoked" in err

    # Step 4: Legitimate client attempting to use RT2 is now rejected
    resp_legit = client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": rt2,
            "client_id": "pulse-web-app",
            "client_secret": "pulse_web_secret_2026",
        },
    )
    assert resp_legit.status_code == 400
    assert resp_legit.get_json()["error"] == "invalid_grant"


def test_refresh_rotation_scope_downscoping_and_exceeding(client, app, seeded_db):
    """Verify downscoping succeeds and exceeding original scopes is rejected."""
    with app.app_context():
        conn = get_db()
        rsa = app.extensions["rsa_manager"]
        user = UserModel.get_by_id(conn, 1)
        tokens = TokenService.issue_tokens(
            conn=conn,
            rsa_manager=rsa,
            issuer="http://127.0.0.1:5000",
            client_id="pulse-web-app",
            scope="openid profile email offline_access",
            user=user,
            include_refresh=True,
        )

    rt = tokens["refresh_token"]

    # Exceeding scope fails
    resp_exceed = client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": rt,
            "scope": "openid profile write:documents",
            "client_id": "pulse-web-app",
            "client_secret": "pulse_web_secret_2026",
        },
    )
    assert resp_exceed.status_code == 400
    assert resp_exceed.get_json()["error"] == "invalid_scope"

    # Valid downscoping succeeds
    resp_down = client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": rt,
            "scope": "openid email",
            "client_id": "pulse-web-app",
            "client_secret": "pulse_web_secret_2026",
        },
    )
    assert resp_down.status_code == 200
    assert resp_down.get_json()["scope"] == "openid email"


def test_refresh_rotation_client_mismatch(client, app, seeded_db):
    """Verify refresh token cannot be used by a different client."""
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

    # pulse-mobile-app attempts to use pulse-web-app's refresh token
    resp = client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": tokens["refresh_token"],
            "client_id": "pulse-mobile-app",
        },
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "invalid_grant"
    assert "different client" in resp.get_json()["error_description"]


def test_refresh_rotation_expired_token(client, app, seeded_db):
    """Verify expired refresh token is rejected."""
    with app.app_context():
        conn = get_db()
        expired = datetime.now(timezone.utc) - timedelta(hours=1)
        TokenModel.create(
            conn=conn,
            token_type="refresh_token",
            raw_token="expired_raw_refresh_token_123",
            client_id="pulse-web-app",
            scope="openid",
            expires_at=expired,
            user_id=1,
            token_family_id="family_exp",
        )

    resp = client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": "expired_raw_refresh_token_123",
            "client_id": "pulse-web-app",
            "client_secret": "pulse_web_secret_2026",
        },
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "invalid_grant"
    assert "expired" in resp.get_json()["error_description"]


def test_refresh_rotation_missing_and_invalid_tokens(client, app, seeded_db):
    """Verify handling of missing and nonexistent refresh tokens."""
    # Missing refresh_token parameter
    resp_missing = client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "client_id": "pulse-web-app",
            "client_secret": "pulse_web_secret_2026",
        },
    )
    assert resp_missing.status_code == 400
    assert resp_missing.get_json()["error"] == "invalid_request"

    # Nonexistent refresh token
    resp_nonexistent = client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": "nonexistent_token_value_xyz",
            "client_id": "pulse-web-app",
            "client_secret": "pulse_web_secret_2026",
        },
    )
    assert resp_nonexistent.status_code == 400
    assert resp_nonexistent.get_json()["error"] == "invalid_grant"


def test_refresh_rotation_unauthorized_grant_type(client, app, seeded_db):
    """Verify client without refresh_token grant permission is rejected."""
    resp = client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": "some_token",
            "client_id": "pulse-m2m-service",
            "client_secret": "pulse_m2m_secret_2026",
        },
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "unauthorized_client"
