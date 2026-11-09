"""Unit tests for TokenService cryptographic generation and verification."""

from datetime import datetime, timezone

import jwt

from app.db.connection import get_db
from app.models.token_model import TokenModel
from app.models.user_model import UserModel
from app.services.token_service import TokenService


def test_generate_access_token(app):
    """Verify RS256 signed access token structure and standard claims."""
    with app.app_context():
        rsa = app.extensions["rsa_manager"]
        issuer = "http://127.0.0.1:5000"

        token, jti, exp = TokenService.generate_access_token(
            rsa_manager=rsa,
            issuer=issuer,
            client_id="pulse-web-app",
            scope="openid profile",
            user_id=1,
            ttl_seconds=3600,
        )

        assert token is not None
        assert jti is not None
        assert exp > datetime.now(timezone.utc)

        # Decode unverified to inspect headers and payload
        headers = jwt.get_unverified_header(token)
        assert headers["alg"] == "RS256"
        assert headers["kid"] == rsa.kid

        decoded = rsa.verify_jwt(token, issuer=issuer)
        assert decoded["iss"] == issuer
        assert decoded["sub"] == "1"
        assert decoded["aud"] == "pulse-web-app"
        assert decoded["client_id"] == "pulse-web-app"
        assert decoded["scope"] == "openid profile"
        assert decoded["token_type"] == "Bearer"
        assert decoded["jti"] == jti


def test_generate_id_token(app, seeded_db):
    """Verify OIDC Core 1.0 ID token claims: nonce, email, profile."""
    with app.app_context():
        conn = get_db()
        rsa = app.extensions["rsa_manager"]
        issuer = "http://127.0.0.1:5000"
        user = UserModel.get_by_email(conn, "developer@pulseauth.dev")

        id_token, exp = TokenService.generate_id_token(
            rsa_manager=rsa,
            issuer=issuer,
            client_id="pulse-web-app",
            user=user,
            scope="openid profile email",
            nonce="test_nonce_789",
            ttl_seconds=3600,
        )

        decoded = rsa.verify_jwt(id_token, issuer=issuer)
        assert decoded["iss"] == issuer
        assert decoded["sub"] == str(user["id"])
        assert decoded["aud"] == "pulse-web-app"
        assert decoded["nonce"] == "test_nonce_789"
        assert decoded["email"] == "developer@pulseauth.dev"
        assert decoded["email_verified"] is True
        assert decoded["name"] == user["full_name"]
        assert decoded["preferred_username"] == "developer"


def test_generate_refresh_token():
    """Verify opaque refresh token randomness and expiration."""
    ref_token, exp = TokenService.generate_refresh_token(ttl_seconds=86400)
    assert len(ref_token) > 50
    assert exp > datetime.now(timezone.utc)


def test_issue_tokens_bundle(app, seeded_db):
    """Verify complete token bundle generation with id_token and refresh_token."""
    with app.app_context():
        conn = get_db()
        rsa = app.extensions["rsa_manager"]
        issuer = "http://127.0.0.1:5000"
        user = UserModel.get_by_email(conn, "developer@pulseauth.dev")

        # Bundle with openid and offline_access
        bundle = TokenService.issue_tokens(
            conn=conn,
            rsa_manager=rsa,
            issuer=issuer,
            client_id="pulse-web-app",
            scope="openid profile offline_access",
            user=user,
            nonce="sample_nonce",
        )

        assert "access_token" in bundle
        assert "token_type" in bundle
        assert bundle["token_type"] == "Bearer"
        assert "expires_in" in bundle
        assert "id_token" in bundle
        assert "refresh_token" in bundle
        assert bundle["scope"] == "openid profile offline_access"

        # Verify access token is valid in database
        valid, rec, err = TokenModel.is_valid(conn, bundle["access_token"])
        assert valid is True
        assert rec["client_id"] == "pulse-web-app"

        # Verify refresh token is valid in database
        valid_r, rec_r, _ = TokenModel.is_valid(conn, bundle["refresh_token"])
        assert valid_r is True
        assert rec_r["token_type"] == "refresh_token"


def test_issue_tokens_client_credentials(app, seeded_db):
    """Verify machine-to-machine service token bundle has no user or refresh token."""
    with app.app_context():
        conn = get_db()
        rsa = app.extensions["rsa_manager"]
        issuer = "http://127.0.0.1:5000"

        bundle = TokenService.issue_tokens(
            conn=conn,
            rsa_manager=rsa,
            issuer=issuer,
            client_id="pulse-m2m-service",
            scope="read:documents write:documents",
            user=None,
        )

        assert "access_token" in bundle
        assert "id_token" not in bundle
        assert "refresh_token" not in bundle


def test_verify_access_token_scenarios(app, seeded_db):
    """Verify access token cryptographic and database revocation verification."""
    with app.app_context():
        conn = get_db()
        rsa = app.extensions["rsa_manager"]
        issuer = "http://127.0.0.1:5000"
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

        # 1. Valid token
        valid, payload, rec, err = TokenService.verify_access_token(
            conn=conn, rsa_manager=rsa, issuer=issuer, raw_token=token
        )
        assert valid is True
        assert payload["sub"] == str(user["id"])
        assert err == ""

        # 2. Revoked token in DB
        TokenModel.revoke(conn, token)
        val_rev, _, _, err_rev = TokenService.verify_access_token(
            conn=conn, rsa_manager=rsa, issuer=issuer, raw_token=token
        )
        assert val_rev is False
        assert "revoked" in err_rev.lower()

        # 3. Tampered token
        tampered = token[:-5] + "XXXXX"
        val_tamp, _, _, err_tamp = TokenService.verify_access_token(
            conn=conn, rsa_manager=rsa, issuer=issuer, raw_token=tampered
        )
        assert val_tamp is False
        assert "not found" in err_tamp.lower()
