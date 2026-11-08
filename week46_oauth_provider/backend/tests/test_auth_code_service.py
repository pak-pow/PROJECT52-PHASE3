"""Unit tests for Authorization Code model and validation service."""

from datetime import datetime, timedelta, timezone

from app.db.connection import get_db
from app.models.auth_code_model import AuthCodeModel
from app.services.auth_code_service import AuthCodeService


def test_auth_code_lifecycle(app, seeded_db):
    """Verify authorization code creation, lookup, and atomic single-use redemption."""
    with app.app_context():
        conn = get_db()

        code_record = AuthCodeModel.create(
            conn=conn,
            client_id="pulse-web-app",
            user_id=1,
            redirect_uri="http://127.0.0.1:3000/callback",
            scope="openid profile",
            ttl_seconds=60,
        )
        assert code_record["code"] is not None
        assert code_record["client_id"] == "pulse-web-app"
        assert code_record["used_at"] is None

        # Validate code is ready for exchange
        valid, fetched, err = AuthCodeModel.validate_code(conn, code_record["code"])
        assert valid is True
        assert err == ""

        # First redemption succeeds
        marked = AuthCodeModel.mark_used(conn, code_record["code"])
        assert marked is True

        # Second redemption attempt fails (single-use enforcement)
        second_marked = AuthCodeModel.mark_used(conn, code_record["code"])
        assert second_marked is False

        # Validate code now reports already redeemed
        valid_again, _, err_again = AuthCodeModel.validate_code(
            conn, code_record["code"]
        )
        assert valid_again is False
        assert "already been redeemed" in err_again


def test_auth_code_expiration(app, seeded_db):
    """Verify expired authorization codes cannot be validated."""
    with app.app_context():
        conn = get_db()

        # Create code with past expiration
        code = "expired_test_code_12345"
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
                code,
                "pulse-web-app",
                1,
                "http://127.0.0.1:3000/callback",
                "openid",
                expired_time,
            ),
        )
        conn.commit()

        valid, _, err = AuthCodeModel.validate_code(conn, code)
        assert valid is False
        assert "expired" in err


def test_auth_code_missing(app, seeded_db):
    """Verify nonexistent code lookup and validation."""
    with app.app_context():
        conn = get_db()
        assert AuthCodeModel.get_by_code(conn, "missing_code") is None
        valid, _, err = AuthCodeModel.validate_code(conn, "missing_code")
        assert valid is False
        assert "Invalid" in err


def test_build_redirect_url():
    """Verify clean URL query parameter construction preserving existing params."""
    base = "https://client.example.com/oauth/cb?mode=dark"
    res = AuthCodeService.build_redirect_url(
        base, {"code": "abc123xyz", "state": "sec_state", "empty": None}
    )
    expected = (
        "https://client.example.com/oauth/cb?mode=dark"
        "&code=abc123xyz&state=sec_state"
    )
    assert res == expected


def test_validate_request_rules(app, seeded_db):
    """Verify parameter validations: client, redirect, scope, PKCE."""
    with app.app_context():
        conn = get_db()

        # Missing client_id
        valid, _, err, desc = AuthCodeService.validate_request(
            conn, "code", None, "http://127.0.0.1:3000/callback", "openid"
        )
        assert not valid
        assert err == "invalid_request"

        # Unknown client_id
        valid, _, err, desc = AuthCodeService.validate_request(
            conn, "code", "unknown_client", "http://127.0.0.1:3000/callback", "openid"
        )
        assert not valid
        assert err == "invalid_client"

        # Missing redirect_uri
        valid, _, err, desc = AuthCodeService.validate_request(
            conn, "code", "pulse-web-app", None, "openid"
        )
        assert not valid
        assert err == "invalid_request"

        # Unregistered redirect_uri
        valid, _, err, desc = AuthCodeService.validate_request(
            conn, "code", "pulse-web-app", "https://attacker.com/cb", "openid"
        )
        assert not valid
        assert err == "invalid_request"
        assert "Unregistered" in desc

        # Missing response_type
        valid, _, err, desc = AuthCodeService.validate_request(
            conn, None, "pulse-web-app", "http://127.0.0.1:3000/callback", "openid"
        )
        assert not valid
        assert err == "invalid_request"

        # Unsupported response_type
        valid, _, err, desc = AuthCodeService.validate_request(
            conn, "token", "pulse-web-app", "http://127.0.0.1:3000/callback", "openid"
        )
        assert not valid
        assert err == "unsupported_response_type"

        # Unauthorized scope
        valid, _, err, desc = AuthCodeService.validate_request(
            conn,
            "code",
            "pulse-web-app",
            "http://127.0.0.1:3000/callback",
            "super:admin",
        )
        assert not valid
        assert err == "invalid_scope"

        # Public client missing PKCE code_challenge
        valid, _, err, desc = AuthCodeService.validate_request(
            conn, "code", "pulse-mobile-app", "http://127.0.0.1:3000/callback", "openid"
        )
        assert not valid
        assert err == "invalid_request"
        assert "Public clients must supply a code_challenge" in desc

        # Public client with invalid code_challenge_method
        valid, _, err, desc = AuthCodeService.validate_request(
            conn,
            "code",
            "pulse-mobile-app",
            "http://127.0.0.1:3000/callback",
            "openid",
            code_challenge="mychallenge",
            code_challenge_method="MD5",
        )
        assert not valid
        assert err == "invalid_request"
        assert "Unsupported code_challenge_method" in desc

        # Valid public client with S256 PKCE
        valid, client, err, desc = AuthCodeService.validate_request(
            conn,
            "code",
            "pulse-mobile-app",
            "http://127.0.0.1:3000/callback",
            "openid",
            code_challenge="mychallenge",
            code_challenge_method="S256",
        )
        assert valid is True
        assert client["client_id"] == "pulse-mobile-app"
