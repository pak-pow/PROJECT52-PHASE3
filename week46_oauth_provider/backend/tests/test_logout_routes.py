"""Unit and integration tests for OpenID Connect RP-Initiated Logout 1.0."""

from app.db.connection import get_db
from app.models.token_model import TokenModel
from app.models.user_model import UserModel
from app.services.token_service import TokenService


def test_logout_get_confirmation_screen_rendered(client):
    """GET /oauth/logout without confirmation returns HTML confirmation screen."""
    res = client.get("/oauth/logout", headers={"Accept": "text/html"})
    assert res.status_code == 200
    assert b"Confirm Logout" in res.data
    assert b"PULSEAUTH RP-INITIATED LOGOUT" in res.data


def test_logout_get_confirmation_with_id_token_hint(client, app, seeded_db):
    """GET /oauth/logout with valid id_token_hint displays user and client context."""
    with app.app_context():
        conn = get_db()
        rsa_mgr = app.extensions["rsa_manager"]
        user = UserModel.get_by_email(conn, "developer@pulseauth.dev")
        id_token, _ = TokenService.generate_id_token(
            rsa_manager=rsa_mgr,
            issuer="http://127.0.0.1:5000",
            client_id="pulse-web-app",
            user=user,
            scope="openid profile email",
        )

    res = client.get(
        f"/oauth/logout?id_token_hint={id_token}",
        headers={"Accept": "text/html"},
    )
    assert res.status_code == 200
    assert b"developer@pulseauth.dev" in res.data
    assert b"PulseWeb Portal" in res.data


def test_logout_tampered_id_token_hint_returns_400(client):
    """Tampered id_token_hint on logout returns HTTP 400 invalid_request."""
    res = client.get("/oauth/logout?id_token_hint=tampered.header.signature")
    assert res.status_code == 400
    data = res.get_json()
    assert data["error"] == "invalid_request"
    assert "Invalid or tampered id_token_hint" in data["error_description"]


def test_logout_mismatched_client_id_returns_400(client, app, seeded_db):
    """Logout with client_id differing from id_token_hint audience returns 400."""
    with app.app_context():
        conn = get_db()
        rsa_mgr = app.extensions["rsa_manager"]
        user = UserModel.get_by_email(conn, "developer@pulseauth.dev")
        id_token, _ = TokenService.generate_id_token(
            rsa_manager=rsa_mgr,
            issuer="http://127.0.0.1:5000",
            client_id="pulse-web-app",
            user=user,
            scope="openid profile email",
        )

    res = client.get(
        f"/oauth/logout?id_token_hint={id_token}&client_id=pulse-mobile-app",
        headers={"Accept": "application/json"},
    )
    assert res.status_code == 400
    data = res.get_json()
    assert data["error"] == "invalid_request"
    assert (
        "client_id does not match id_token_hint audience" in data["error_description"]
    )


def test_logout_unregistered_post_logout_redirect_uri_returns_400(
    client, app, seeded_db
):
    """Unregistered post_logout_redirect_uri is rejected with HTTP 400."""
    with app.app_context():
        conn = get_db()
        rsa_mgr = app.extensions["rsa_manager"]
        user = UserModel.get_by_email(conn, "developer@pulseauth.dev")
        id_token, _ = TokenService.generate_id_token(
            rsa_manager=rsa_mgr,
            issuer="http://127.0.0.1:5000",
            client_id="pulse-web-app",
            user=user,
            scope="openid profile email",
        )

    res = client.get(
        f"/oauth/logout?id_token_hint={id_token}"
        "&post_logout_redirect_uri=https://malicious-phishing.com/callback",
        headers={"Accept": "application/json"},
    )
    assert res.status_code == 400
    data = res.get_json()
    assert data["error"] == "invalid_request"
    assert "Unregistered post_logout_redirect_uri" in data["error_description"]


def test_logout_cannot_validate_post_logout_uri_without_client(client):
    """Post logout URI without client context returns HTTP 400 invalid_request."""
    res = client.get(
        "/oauth/logout?post_logout_redirect_uri=http://127.0.0.1:3000/callback",
        headers={"Accept": "application/json"},
    )
    assert res.status_code == 400
    data = res.get_json()
    assert data["error"] == "invalid_request"
    assert "Cannot validate post_logout_redirect_uri" in data["error_description"]


def test_logout_post_success_redirects_and_revokes_tokens(client, app, seeded_db):
    """POST /oauth/logout revokes active user tokens and redirects to callback."""
    with app.app_context():
        conn = get_db()
        rsa_mgr = app.extensions["rsa_manager"]
        user = UserModel.get_by_email(conn, "developer@pulseauth.dev")

        # Issue active tokens for the user
        bundle = TokenService.issue_tokens(
            conn=conn,
            rsa_manager=rsa_mgr,
            issuer="http://127.0.0.1:5000",
            client_id="pulse-web-app",
            scope="openid profile email offline_access",
            user=user,
            include_refresh=True,
        )
        id_token = bundle["id_token"]
        access_token = bundle["access_token"]

        # Confirm token is currently valid
        valid_before, _, _ = TokenModel.is_valid(conn, access_token)
        assert valid_before is True

    # Execute logout
    res = client.post(
        "/oauth/logout",
        data={
            "id_token_hint": id_token,
            "post_logout_redirect_uri": "http://127.0.0.1:3000/callback",
            "state": "logout_state_123",
            "confirm": "true",
        },
    )
    assert res.status_code == 302
    assert "http://127.0.0.1:3000/callback" in res.headers["Location"]
    assert "state=logout_state_123" in res.headers["Location"]

    # Verify user tokens were revoked in database
    with app.app_context():
        conn = get_db()
        valid_after, record, reason = TokenModel.is_valid(conn, access_token)
        assert valid_after is False
        assert "revoked" in reason.lower()


def test_logout_post_json_api_response(client, app, seeded_db):
    """POST /oauth/logout with JSON request returns 200 OK with redirect_uri."""
    with app.app_context():
        conn = get_db()
        rsa_mgr = app.extensions["rsa_manager"]
        user = UserModel.get_by_email(conn, "developer@pulseauth.dev")
        id_token, _ = TokenService.generate_id_token(
            rsa_manager=rsa_mgr,
            issuer="http://127.0.0.1:5000",
            client_id="pulse-web-app",
            user=user,
            scope="openid profile email",
        )

    res = client.post(
        "/oauth/logout",
        json={
            "id_token_hint": id_token,
            "post_logout_redirect_uri": "http://127.0.0.1:3000/callback",
            "state": "json_state_456",
        },
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "logged_out"
    assert "http://127.0.0.1:3000/callback?state=json_state_456" in data["redirect_uri"]


def test_logout_get_confirmed_via_query_param(client, app, seeded_db):
    """GET /oauth/logout with confirm=true executes immediate logout."""
    with app.app_context():
        conn = get_db()
        rsa_mgr = app.extensions["rsa_manager"]
        user = UserModel.get_by_email(conn, "developer@pulseauth.dev")
        id_token, _ = TokenService.generate_id_token(
            rsa_manager=rsa_mgr,
            issuer="http://127.0.0.1:5000",
            client_id="pulse-web-app",
            user=user,
            scope="openid profile email",
        )

    res = client.get(
        f"/oauth/logout?confirm=true&id_token_hint={id_token}"
        "&post_logout_redirect_uri=http://127.0.0.1:3000/callback",
    )
    assert res.status_code == 302
    assert "http://127.0.0.1:3000/callback" in res.headers["Location"]


def test_logout_without_redirect_uri_renders_completed_screen(client, app, seeded_db):
    """POST /oauth/logout without redirect_uri displays session terminated screen."""
    with app.app_context():
        conn = get_db()
        rsa_mgr = app.extensions["rsa_manager"]
        user = UserModel.get_by_email(conn, "developer@pulseauth.dev")
        id_token, _ = TokenService.generate_id_token(
            rsa_manager=rsa_mgr,
            issuer="http://127.0.0.1:5000",
            client_id="pulse-web-app",
            user=user,
            scope="openid profile email",
        )

    # HTML request
    res = client.post(
        "/oauth/logout",
        data={"id_token_hint": id_token, "confirm": "true"},
        headers={"Accept": "text/html"},
    )
    assert res.status_code == 200
    assert b"Session Terminated" in res.data
    assert b"LOGGED OUT" in res.data

    # JSON request
    res_json = client.post(
        "/oauth/logout",
        json={"id_token_hint": id_token, "confirm": "true"},
    )
    assert res_json.status_code == 200
    assert res_json.get_json()["status"] == "logged_out"
