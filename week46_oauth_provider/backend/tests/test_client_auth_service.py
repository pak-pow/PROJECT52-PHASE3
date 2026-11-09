"""Unit tests for ClientAuthService authentication and header parsing."""

import base64

from app.db.connection import get_db
from app.services.client_auth_service import ClientAuthService


def test_client_auth_basic_header_malformed(app):
    """Verify malformed Basic Authorization headers are detected."""
    with app.test_request_context(
        "/oauth/token",
        headers={"Authorization": "Basic !!!not_valid_base64!!!"},
    ) as ctx:
        cid, sec, method = ClientAuthService.extract_credentials(ctx.request)
        assert method == "basic_malformed"

    # Base64 string without colon
    no_colon_b64 = base64.b64encode(b"just_client_id_no_colon").decode()
    with app.test_request_context(
        "/oauth/token",
        headers={"Authorization": f"Basic {no_colon_b64}"},
    ) as ctx:
        cid, sec, method = ClientAuthService.extract_credentials(ctx.request)
        assert method == "basic_malformed"


def test_client_auth_authenticate_malformed_header(app, seeded_db):
    """Verify authenticate returns 401 on malformed basic auth header."""
    with app.app_context():
        conn = get_db()
        with app.test_request_context(
            "/oauth/token",
            headers={"Authorization": "Basic ???bad_base64???"},
        ) as ctx:
            val, cl, err, desc, status = ClientAuthService.authenticate(
                conn, ctx.request
            )
            assert val is False
            assert status == 401
            assert err == "invalid_client"
            assert "Malformed" in desc


def test_client_auth_missing_client_id(app, seeded_db):
    """Verify missing client identifier returns appropriate error."""
    with app.app_context():
        conn = get_db()
        with app.test_request_context("/oauth/token", data={}) as ctx:
            val, cl, err, desc, status = ClientAuthService.authenticate(
                conn, ctx.request
            )
            assert val is False
            assert status == 400
            assert err == "invalid_client"
            assert "Missing client_id" in desc


def test_client_auth_client_not_found(app, seeded_db):
    """Verify unknown client returns 401 invalid_client."""
    with app.app_context():
        conn = get_db()
        with app.test_request_context(
            "/oauth/token",
            data={"client_id": "nonexistent-client-id-123"},
        ) as ctx:
            val, cl, err, desc, status = ClientAuthService.authenticate(
                conn, ctx.request
            )
            assert val is False
            assert status == 401
            assert err == "invalid_client"
            assert "not found" in desc.lower()


def test_client_auth_public_client_with_secret_rejected(app, seeded_db):
    """Verify public clients supplying a client_secret are rejected."""
    with app.app_context():
        conn = get_db()
        with app.test_request_context(
            "/oauth/token",
            data={
                "client_id": "pulse-mobile-app",
                "client_secret": "illegal_secret_for_public_client",
            },
        ) as ctx:
            val, cl, err, desc, status = ClientAuthService.authenticate(
                conn, ctx.request
            )
            assert val is False
            assert status == 401
            assert err == "invalid_client"
            assert "must not supply" in desc


def test_client_auth_public_client_disallowed_on_m2m(app, seeded_db):
    """Verify public clients are rejected when allow_public=False."""
    with app.app_context():
        conn = get_db()
        with app.test_request_context(
            "/oauth/token",
            data={"client_id": "pulse-mobile-app"},
        ) as ctx:
            val, cl, err, desc, status = ClientAuthService.authenticate(
                conn, ctx.request, allow_public=False
            )
            assert val is False
            assert status == 400
            assert err == "unauthorized_client"


def test_client_auth_confidential_client_missing_secret(app, seeded_db):
    """Verify confidential client without secret returns 401."""
    with app.app_context():
        conn = get_db()
        with app.test_request_context(
            "/oauth/token",
            data={"client_id": "pulse-web-app"},
        ) as ctx:
            val, cl, err, desc, status = ClientAuthService.authenticate(
                conn, ctx.request
            )
            assert val is False
            assert status == 401
            assert err == "invalid_client"
            assert "require client_secret" in desc
