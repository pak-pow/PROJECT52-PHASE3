"""Unit and integration tests for RFC 8707 Resource Indicators for OAuth 2.0."""

import jwt

from app.db.connection import get_db
from app.models.auth_code_model import AuthCodeModel
from app.models.client_model import ClientModel
from app.models.user_model import UserModel
from app.services.auth_code_service import AuthCodeService
from app.services.refresh_service import RefreshTokenService
from app.services.token_guard import require_oauth_token
from app.services.token_service import TokenService


def test_validate_resource_indicators_helper():
    """Verify validate_resource helper handles absolute URIs and fragments."""
    # Valid absolute URIs
    valid_https, _ = AuthCodeService.validate_resource(
        "https://api.pulseauth.dev/v1/documents"
    )
    assert valid_https is True

    valid_http, _ = AuthCodeService.validate_resource(
        "http://127.0.0.1:5000/api/v1/resource"
    )
    assert valid_http is True

    # Empty / None is allowed (optional parameter)
    valid_none, _ = AuthCodeService.validate_resource(None)
    assert valid_none is True

    # Invalid: relative URI
    invalid_rel, err1 = AuthCodeService.validate_resource("/api/v1/documents")
    assert invalid_rel is False
    assert "absolute URI" in err1

    # Invalid: URI containing fragment
    invalid_frag, err2 = AuthCodeService.validate_resource(
        "https://api.pulseauth.dev/v1/documents#section"
    )
    assert invalid_frag is False
    assert "fragment" in err2


def test_authorize_request_with_invalid_resource_rejected(client, seeded_db):
    """Authorize request with invalid resource redirects with error=invalid_target."""
    res = client.get(
        "/oauth/authorize?response_type=code"
        "&client_id=pulse-web-app"
        "&redirect_uri=http://127.0.0.1:3000/callback"
        "&scope=openid"
        "&resource=invalid-relative-uri#frag",
    )
    assert res.status_code == 302
    assert "error=invalid_target" in res.headers["Location"]


def test_authorization_code_flow_with_resource_indicator(client, app, seeded_db):
    """Full auth code flow with resource parameter binds target to issued JWT."""
    target_resource = "http://127.0.0.1:5000/api/v1/resource/documents"

    # 1. Authorize with resource indicator
    auth_res = client.post(
        "/oauth/authorize",
        data={
            "response_type": "code",
            "client_id": "pulse-web-app",
            "redirect_uri": "http://127.0.0.1:3000/callback",
            "scope": "openid profile email read:documents",
            "email": "developer@pulseauth.dev",
            "password": "DevPass2026!",
            "action": "approve",
            "resource": target_resource,
        },
    )
    assert auth_res.status_code == 302
    location = auth_res.headers["Location"]
    code = location.split("code=")[1].split("&")[0]

    # Verify resource is stored in auth code database record
    with app.app_context():
        conn = get_db()
        code_rec = AuthCodeModel.get_by_code(conn, code)
        assert code_rec is not None
        assert code_rec["resource"] == target_resource

    # 2. Exchange code for tokens
    token_res = client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "http://127.0.0.1:3000/callback",
            "client_id": "pulse-web-app",
            "client_secret": "pulse_web_secret_2026",
            "resource": target_resource,
        },
    )
    assert token_res.status_code == 200
    tokens = token_res.get_json()
    access_token = tokens["access_token"]

    # Decode and inspect access token claims
    unverified = jwt.decode(access_token, options={"verify_signature": False})
    assert unverified["resource"] == target_resource
    assert target_resource in unverified["aud"]


def test_authorization_code_token_exchange_resource_mismatch_rejected(
    client, app, seeded_db
):
    """Exchanging code with a different resource than authorized returns 400."""
    authorized_resource = "http://127.0.0.1:5000/api/v1/resource/documents"
    mismatched_resource = "http://127.0.0.1:5000/api/v1/resource/invoices"

    # Authorize with first resource
    auth_res = client.post(
        "/oauth/authorize",
        data={
            "response_type": "code",
            "client_id": "pulse-web-app",
            "redirect_uri": "http://127.0.0.1:3000/callback",
            "scope": "openid read:documents",
            "email": "developer@pulseauth.dev",
            "password": "DevPass2026!",
            "action": "approve",
            "resource": authorized_resource,
        },
    )
    code = auth_res.headers["Location"].split("code=")[1].split("&")[0]

    # Attempt exchange with different resource
    token_res = client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "http://127.0.0.1:3000/callback",
            "client_id": "pulse-web-app",
            "client_secret": "pulse_web_secret_2026",
            "resource": mismatched_resource,
        },
    )
    assert token_res.status_code == 400
    data = token_res.get_json()
    assert data["error"] == "invalid_target"


def test_client_credentials_with_resource_indicator(client, seeded_db):
    """Client credentials grant binds requested resource indicator to access token."""
    target_resource = "http://127.0.0.1:5000/api/v1/resource/documents"

    res = client.post(
        "/oauth/token",
        data={
            "grant_type": "client_credentials",
            "client_id": "pulse-m2m-service",
            "client_secret": "pulse_m2m_secret_2026",
            "scope": "read:documents",
            "resource": target_resource,
        },
    )
    assert res.status_code == 200
    tokens = res.get_json()
    unverified = jwt.decode(tokens["access_token"], options={"verify_signature": False})
    assert unverified["resource"] == target_resource
    assert target_resource in unverified["aud"]


def test_token_guard_expected_resource_enforcement(client, app, seeded_db):
    """TokenGuard validates audience/resource matches expected target server."""
    target_res = "http://127.0.0.1:5000/api/v1/resource/documents"
    other_res = "http://127.0.0.1:5000/api/v1/billing"

    # Add dynamic test route with expected_resource
    @app.route("/api/test-guarded-resource", methods=["GET"])
    @require_oauth_token(
        required_scopes=["read:documents"], expected_resource=target_res
    )
    def test_guarded():
        return {"status": "authorized"}, 200

    with app.app_context():
        conn = get_db()
        rsa_mgr = app.extensions["rsa_manager"]
        user = UserModel.get_by_email(conn, "developer@pulseauth.dev")

        # Token 1: issued for target_res
        valid_bundle = TokenService.issue_tokens(
            conn=conn,
            rsa_manager=rsa_mgr,
            issuer="http://127.0.0.1:5000",
            client_id="pulse-web-app",
            scope="read:documents",
            user=user,
            resource=target_res,
        )
        token_valid = valid_bundle["access_token"]

        # Token 2: issued for other_res
        mismatched_bundle = TokenService.issue_tokens(
            conn=conn,
            rsa_manager=rsa_mgr,
            issuer="http://127.0.0.1:5000",
            client_id="pulse-web-app",
            scope="read:documents",
            user=user,
            resource=other_res,
        )
        token_mismatched = mismatched_bundle["access_token"]

    # Call with valid target resource token -> 200 OK
    res_ok = client.get(
        "/api/test-guarded-resource",
        headers={"Authorization": f"Bearer {token_valid}"},
    )
    assert res_ok.status_code == 200
    assert res_ok.get_json()["status"] == "authorized"

    # Call with mismatched resource token -> 401 invalid_token
    res_err = client.get(
        "/api/test-guarded-resource",
        headers={"Authorization": f"Bearer {token_mismatched}"},
    )
    assert res_err.status_code == 401
    assert res_err.get_json()["error"] == "invalid_token"
    assert (
        "audience does not match target resource"
        in res_err.get_json()["error_description"]
    )


def test_refresh_token_preserves_resource_indicator(client, app, seeded_db):
    """Refreshing a token preserves the bound resource indicator in rotated tokens."""
    target_resource = "http://127.0.0.1:5000/api/v1/resource/documents"

    with app.app_context():
        conn = get_db()
        rsa_mgr = app.extensions["rsa_manager"]
        user = UserModel.get_by_email(conn, "developer@pulseauth.dev")
        client_rec = ClientModel.get_by_client_id(conn, "pulse-web-app")

        # Issue initial tokens with resource
        initial_bundle = TokenService.issue_tokens(
            conn=conn,
            rsa_manager=rsa_mgr,
            issuer="http://127.0.0.1:5000",
            client_id="pulse-web-app",
            scope="openid read:documents offline_access",
            user=user,
            include_refresh=True,
            resource=target_resource,
        )
        refresh_token = initial_bundle["refresh_token"]

        # Rotate the refresh token
        success, new_bundle, _, _, _ = RefreshTokenService.rotate_token(
            conn=conn,
            rsa_manager=rsa_mgr,
            issuer="http://127.0.0.1:5000",
            client=client_rec,
            refresh_token=refresh_token,
        )
        assert success is True
        assert new_bundle is not None

        # Verify rotated access token retains target resource
        unverified = jwt.decode(
            new_bundle["access_token"], options={"verify_signature": False}
        )
        assert unverified["resource"] == target_resource
        assert target_resource in unverified["aud"]
