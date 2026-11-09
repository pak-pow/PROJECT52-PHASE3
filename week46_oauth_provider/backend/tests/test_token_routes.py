"""Integration tests for POST /oauth/token endpoint."""

import base64
from datetime import datetime, timedelta, timezone

from app.db.connection import get_db
from app.models.auth_code_model import AuthCodeModel
from app.services.pkce_service import PKCEService


def test_token_missing_grant_type(client):
    """Verify missing grant_type returns 400 invalid_request."""
    resp = client.post("/oauth/token", data={})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "invalid_request"


def test_token_unsupported_grant_type(client):
    """Verify unsupported grant_type returns 400 unsupported_grant_type."""
    resp = client.post("/oauth/token", data={"grant_type": "implicit"})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "unsupported_grant_type"


def test_token_auth_code_confidential_client_success(client, app, seeded_db):
    """Verify authorization_code grant exchange for confidential client."""
    with app.app_context():
        conn = get_db()
        code_rec = AuthCodeModel.create(
            conn=conn,
            client_id="pulse-web-app",
            user_id=1,
            redirect_uri="http://127.0.0.1:3000/callback",
            scope="openid profile offline_access",
            ttl_seconds=60,
            nonce="my_nonce_123",
        )

    payload = {
        "grant_type": "authorization_code",
        "code": code_rec["code"],
        "redirect_uri": "http://127.0.0.1:3000/callback",
        "client_id": "pulse-web-app",
        "client_secret": "pulse_web_secret_2026",
    }
    resp = client.post("/oauth/token", data=payload)
    assert resp.status_code == 200
    data = resp.get_json()
    assert "access_token" in data
    assert data["token_type"] == "Bearer"
    assert "id_token" in data
    assert "refresh_token" in data
    assert resp.headers["Cache-Control"] == "no-store"


def test_token_auth_code_http_basic_auth(client, app, seeded_db):
    """Verify client authentication via HTTP Basic Authorization header."""
    with app.app_context():
        conn = get_db()
        code_rec = AuthCodeModel.create(
            conn=conn,
            client_id="pulse-web-app",
            user_id=1,
            redirect_uri="http://127.0.0.1:3000/callback",
            scope="openid",
            ttl_seconds=60,
        )

    creds = base64.b64encode(b"pulse-web-app:pulse_web_secret_2026").decode()
    headers = {"Authorization": f"Basic {creds}"}
    payload = {
        "grant_type": "authorization_code",
        "code": code_rec["code"],
        "redirect_uri": "http://127.0.0.1:3000/callback",
    }
    resp = client.post("/oauth/token", data=payload, headers=headers)
    assert resp.status_code == 200
    assert "access_token" in resp.get_json()


def test_token_auth_code_public_client_pkce_s256(client, app, seeded_db):
    """Verify public client authorization code exchange with S256 PKCE."""
    verifier = PKCEService.generate_verifier(64)
    challenge = PKCEService.compute_challenge(verifier, method="S256")

    with app.app_context():
        conn = get_db()
        code_rec = AuthCodeModel.create(
            conn=conn,
            client_id="pulse-mobile-app",
            user_id=1,
            redirect_uri="http://127.0.0.1:3000/callback",
            scope="openid profile",
            ttl_seconds=60,
            code_challenge=challenge,
            code_challenge_method="S256",
        )

    payload = {
        "grant_type": "authorization_code",
        "client_id": "pulse-mobile-app",
        "code": code_rec["code"],
        "redirect_uri": "http://127.0.0.1:3000/callback",
        "code_verifier": verifier,
    }
    resp = client.post("/oauth/token", json=payload)
    assert resp.status_code == 200
    data = resp.get_json()
    assert "access_token" in data
    assert "id_token" in data


def test_token_auth_code_public_client_pkce_plain(client, app, seeded_db):
    """Verify public client authorization code exchange with plain PKCE."""
    verifier = PKCEService.generate_verifier(64)
    challenge = PKCEService.compute_challenge(verifier, method="plain")

    with app.app_context():
        conn = get_db()
        code_rec = AuthCodeModel.create(
            conn=conn,
            client_id="pulse-mobile-app",
            user_id=1,
            redirect_uri="http://127.0.0.1:3000/callback",
            scope="openid",
            ttl_seconds=60,
            code_challenge=challenge,
            code_challenge_method="plain",
        )

    payload = {
        "grant_type": "authorization_code",
        "client_id": "pulse-mobile-app",
        "code": code_rec["code"],
        "redirect_uri": "http://127.0.0.1:3000/callback",
        "code_verifier": verifier,
    }
    resp = client.post("/oauth/token", data=payload)
    assert resp.status_code == 200
    assert "access_token" in resp.get_json()


def test_token_auth_code_pkce_verifier_failures(client, app, seeded_db):
    """Verify missing and invalid code_verifier are rejected with 400 invalid_grant."""
    verifier = PKCEService.generate_verifier(64)
    challenge = PKCEService.compute_challenge(verifier, method="S256")

    with app.app_context():
        conn = get_db()
        code_rec = AuthCodeModel.create(
            conn=conn,
            client_id="pulse-mobile-app",
            user_id=1,
            redirect_uri="http://127.0.0.1:3000/callback",
            scope="openid",
            ttl_seconds=60,
            code_challenge=challenge,
            code_challenge_method="S256",
        )

    # 1. Missing code_verifier
    payload_missing = {
        "grant_type": "authorization_code",
        "client_id": "pulse-mobile-app",
        "code": code_rec["code"],
        "redirect_uri": "http://127.0.0.1:3000/callback",
    }
    resp_missing = client.post("/oauth/token", data=payload_missing)
    assert resp_missing.status_code == 400
    assert resp_missing.get_json()["error"] == "invalid_grant"
    assert "Missing 'code_verifier'" in resp_missing.get_json()["error_description"]

    # 2. Wrong code_verifier
    payload_wrong = dict(payload_missing)
    payload_wrong["code_verifier"] = (
        "incorrect_verifier_that_does_not_match_at_all_12345"
    )
    resp_wrong = client.post("/oauth/token", data=payload_wrong)
    assert resp_wrong.status_code == 400
    assert resp_wrong.get_json()["error"] == "invalid_grant"
    assert "PKCE verification failed" in resp_wrong.get_json()["error_description"]


def test_token_auth_code_expired_and_replay_attacks(client, app, seeded_db):
    """Verify expired codes fail and redeemed codes cannot be replayed."""
    with app.app_context():
        conn = get_db()
        # Create expired code
        expired_time = (datetime.now(timezone.utc) - timedelta(seconds=10)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO authorization_codes (
                code, client_id, user_id, redirect_uri, scope, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "expired_code_xyz",
                "pulse-web-app",
                1,
                "http://127.0.0.1:3000/callback",
                "openid",
                expired_time,
            ),
        )
        conn.commit()

        # Create valid code
        valid_rec = AuthCodeModel.create(
            conn=conn,
            client_id="pulse-web-app",
            user_id=1,
            redirect_uri="http://127.0.0.1:3000/callback",
            scope="openid",
            ttl_seconds=60,
        )

    # Expired code fails
    resp_exp = client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": "pulse-web-app",
            "client_secret": "pulse_web_secret_2026",
            "code": "expired_code_xyz",
            "redirect_uri": "http://127.0.0.1:3000/callback",
        },
    )
    assert resp_exp.status_code == 400
    assert "expired" in resp_exp.get_json()["error_description"]

    # First valid redemption succeeds
    payload_valid = {
        "grant_type": "authorization_code",
        "client_id": "pulse-web-app",
        "client_secret": "pulse_web_secret_2026",
        "code": valid_rec["code"],
        "redirect_uri": "http://127.0.0.1:3000/callback",
    }
    resp_first = client.post("/oauth/token", data=payload_valid)
    assert resp_first.status_code == 200

    # Second redemption attempt fails (single-use replay prevention)
    resp_replay = client.post("/oauth/token", data=payload_valid)
    assert resp_replay.status_code == 400
    assert "already been redeemed" in resp_replay.get_json()["error_description"]


def test_token_auth_code_parameter_mismatches(client, app, seeded_db):
    """Verify mismatched redirect_uri or client_id are rejected."""
    with app.app_context():
        conn = get_db()
        code_rec = AuthCodeModel.create(
            conn=conn,
            client_id="pulse-web-app",
            user_id=1,
            redirect_uri="http://127.0.0.1:3000/callback",
            scope="openid",
            ttl_seconds=60,
        )

    # Mismatched redirect_uri
    resp_bad_uri = client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": "pulse-web-app",
            "client_secret": "pulse_web_secret_2026",
            "code": code_rec["code"],
            "redirect_uri": "http://127.0.0.1:3000/wrong_callback",
        },
    )
    assert resp_bad_uri.status_code == 400
    assert "redirect_uri does not match" in resp_bad_uri.get_json()["error_description"]

    # Mismatched client_id
    resp_bad_client = client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": "pulse-mobile-app",
            "code": code_rec["code"],
            "redirect_uri": "http://127.0.0.1:3000/callback",
        },
    )
    assert resp_bad_client.status_code == 400
    assert "different client" in resp_bad_client.get_json()["error_description"]


def test_token_auth_code_missing_parameters(client, seeded_db):
    """Verify missing code or redirect_uri parameters return 400."""
    # Missing code
    resp1 = client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": "pulse-web-app",
            "client_secret": "pulse_web_secret_2026",
            "redirect_uri": "http://127.0.0.1:3000/callback",
        },
    )
    assert resp1.status_code == 400
    assert "Missing 'code'" in resp1.get_json()["error_description"]

    # Missing redirect_uri
    resp2 = client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": "pulse-web-app",
            "client_secret": "pulse_web_secret_2026",
            "code": "some_code",
        },
    )
    assert resp2.status_code == 400
    assert "Missing 'redirect_uri'" in resp2.get_json()["error_description"]


def test_token_client_credentials_grant(client, seeded_db):
    """Verify client_credentials machine-to-machine token issuance and permissions."""
    # 1. Success with explicit scope
    resp = client.post(
        "/oauth/token",
        data={
            "grant_type": "client_credentials",
            "client_id": "pulse-m2m-service",
            "client_secret": "pulse_m2m_secret_2026",
            "scope": "read:documents",
        },
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert "access_token" in data
    assert data["token_type"] == "Bearer"
    assert data["scope"] == "read:documents"

    # 2. Success with default scopes (omitted scope)
    resp_def = client.post(
        "/oauth/token",
        data={
            "grant_type": "client_credentials",
            "client_id": "pulse-m2m-service",
            "client_secret": "pulse_m2m_secret_2026",
        },
    )
    assert resp_def.status_code == 200
    assert "read:documents write:documents" in resp_def.get_json()["scope"]

    # 3. Public client cannot use client_credentials
    resp_pub = client.post(
        "/oauth/token",
        data={
            "grant_type": "client_credentials",
            "client_id": "pulse-mobile-app",
        },
    )
    assert resp_pub.status_code == 400
    assert resp_pub.get_json()["error"] == "unauthorized_client"

    # 4. Scope exceeding client permissions
    resp_scope = client.post(
        "/oauth/token",
        data={
            "grant_type": "client_credentials",
            "client_id": "pulse-m2m-service",
            "client_secret": "pulse_m2m_secret_2026",
            "scope": "super:admin",
        },
    )
    assert resp_scope.status_code == 400
    assert resp_scope.get_json()["error"] == "invalid_scope"

    # 5. Invalid client secret
    resp_sec = client.post(
        "/oauth/token",
        data={
            "grant_type": "client_credentials",
            "client_id": "pulse-m2m-service",
            "client_secret": "wrong_secret_123",
        },
    )
    assert resp_sec.status_code == 401
    assert resp_sec.get_json()["error"] == "invalid_client"
