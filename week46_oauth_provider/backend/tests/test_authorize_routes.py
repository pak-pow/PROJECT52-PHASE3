"""Integration tests for GET & POST /oauth/authorize endpoints."""

import urllib.parse

from app.db.connection import get_db
from app.models.consent_model import ConsentModel
from app.models.user_model import UserModel


def test_authorize_get_invalid_redirect_uri_returns_400(client, seeded_db):
    """Verify unregistered redirect_uri returns HTTP 400 Bad Request."""
    url = (
        "/oauth/authorize?response_type=code"
        "&client_id=pulse-web-app&redirect_uri=https://malicious.com"
    )
    resp = client.get(url)
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["error"] == "invalid_request"
    assert "Unregistered or invalid redirect_uri" in data["error_description"]


def test_authorize_get_unknown_client_returns_400(client, seeded_db):
    """Verify unknown client_id returns HTTP 400 Bad Request."""
    url = (
        "/oauth/authorize?response_type=code"
        "&client_id=unknown-client"
        "&redirect_uri=http://127.0.0.1:3000/callback"
    )
    resp = client.get(url)
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["error"] == "invalid_client"


def test_authorize_get_unsupported_response_type_redirects(client, seeded_db):
    """Verify valid client with invalid response_type redirects to callback."""
    url = (
        "/oauth/authorize?response_type=token"
        "&client_id=pulse-web-app"
        "&redirect_uri=http://127.0.0.1:3000/callback"
        "&state=test_state"
    )
    resp = client.get(url)
    assert resp.status_code == 302
    target = resp.headers["Location"]
    parsed = urllib.parse.urlparse(target)
    queries = dict(urllib.parse.parse_qsl(parsed.query))
    assert queries["error"] == "unsupported_response_type"
    assert queries["state"] == "test_state"


def test_authorize_get_public_client_missing_pkce_redirects(client, seeded_db):
    """Verify public client without PKCE challenge redirects with invalid_request."""
    url = (
        "/oauth/authorize?response_type=code"
        "&client_id=pulse-mobile-app"
        "&redirect_uri=http://127.0.0.1:3000/callback"
        "&state=mob_state"
    )
    resp = client.get(url)
    assert resp.status_code == 302
    queries = dict(
        urllib.parse.parse_qsl(urllib.parse.urlparse(resp.headers["Location"]).query)
    )
    assert queries["error"] == "invalid_request"
    assert "Public clients must supply a code_challenge" in queries["error_description"]
    assert queries["state"] == "mob_state"


def test_authorize_get_json_consent_required(client, seeded_db):
    """Verify GET /oauth/authorize returns consent prompt when JSON requested."""
    url = (
        "/oauth/authorize?response_type=code"
        "&client_id=pulse-web-app"
        "&redirect_uri=http://127.0.0.1:3000/callback"
        "&scope=openid%20profile"
        "&state=xyz123"
    )
    resp = client.get(url, headers={"Accept": "application/json"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "consent_required"
    assert data["client_id"] == "pulse-web-app"
    assert data["client_name"] == "PulseWeb Portal (Confidential)"
    assert set(data["scopes"]) == {"openid", "profile"}
    assert data["state"] == "xyz123"


def test_authorize_get_html_consent_screen(client, seeded_db):
    """Verify HTML consent form is rendered for browser user-agent."""
    url = (
        "/oauth/authorize?response_type=code"
        "&client_id=pulse-web-app"
        "&redirect_uri=http://127.0.0.1:3000/callback"
        "&scope=openid%20profile"
    )
    resp = client.get(url, headers={"Accept": "text/html"})
    assert resp.status_code == 200
    assert b"PulseWeb Portal (Confidential)" in resp.data
    assert b"openid" in resp.data
    assert b"Approve & Continue" in resp.data


def test_authorize_get_pre_authenticated_with_consent_redirects_code(
    client, app, seeded_db
):
    """Verify pre-authenticated user with existing consent immediately gets code."""
    with app.app_context():
        conn = get_db()
        user = UserModel.get_by_email(conn, "developer@pulseauth.dev")
        ConsentModel.grant_consent(
            conn, user["id"], "pulse-web-app", ["openid", "profile"]
        )

    url = (
        f"/oauth/authorize?response_type=code"
        f"&client_id=pulse-web-app"
        f"&redirect_uri=http://127.0.0.1:3000/callback"
        f"&scope=openid%20profile"
        f"&state=direct_state"
        f"&user_id={user['id']}"
    )
    resp = client.get(url)
    assert resp.status_code == 302
    queries = dict(
        urllib.parse.parse_qsl(urllib.parse.urlparse(resp.headers["Location"]).query)
    )
    assert "code" in queries
    assert queries["state"] == "direct_state"


def test_authorize_post_deny_redirects_access_denied(client, seeded_db):
    """Verify user denying consent redirects with access_denied error."""
    payload = {
        "client_id": "pulse-web-app",
        "redirect_uri": "http://127.0.0.1:3000/callback",
        "response_type": "code",
        "scope": "openid",
        "state": "deny_state",
        "action": "deny",
    }
    resp = client.post("/oauth/authorize", data=payload)
    assert resp.status_code == 302
    queries = dict(
        urllib.parse.parse_qsl(urllib.parse.urlparse(resp.headers["Location"]).query)
    )
    assert queries["error"] == "access_denied"
    assert queries["state"] == "deny_state"


def test_authorize_post_invalid_credentials(client, seeded_db):
    """Verify wrong password returns 401 on JSON and re-renders form on HTML."""
    # JSON request
    payload = {
        "client_id": "pulse-web-app",
        "redirect_uri": "http://127.0.0.1:3000/callback",
        "response_type": "code",
        "scope": "openid",
        "email": "developer@pulseauth.dev",
        "password": "WrongPassword123!",
        "action": "approve",
    }
    resp = client.post("/oauth/authorize", json=payload)
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "access_denied"

    # HTML form request
    html_resp = client.post("/oauth/authorize", data=payload)
    assert html_resp.status_code == 200
    assert b"Invalid email or password" in html_resp.data


def test_authorize_post_success_confidential_client(client, seeded_db):
    """Verify successful approval issues code and redirects to callback."""
    payload = {
        "client_id": "pulse-web-app",
        "redirect_uri": "http://127.0.0.1:3000/callback",
        "response_type": "code",
        "scope": "openid profile email",
        "state": "secret_state_123",
        "email": "developer@pulseauth.dev",
        "password": "DevPass2026!",
        "action": "approve",
    }
    resp = client.post("/oauth/authorize", data=payload)
    assert resp.status_code == 302
    queries = dict(
        urllib.parse.parse_qsl(urllib.parse.urlparse(resp.headers["Location"]).query)
    )
    assert "code" in queries
    assert len(queries["code"]) > 20
    assert queries["state"] == "secret_state_123"


def test_authorize_post_success_public_client_with_pkce(client, seeded_db):
    """Verify public client with PKCE S256 succeeds on JSON POST."""
    from app.services.pkce_service import PKCEService

    verifier = PKCEService.generate_verifier(64)
    challenge = PKCEService.compute_challenge(verifier, method="S256")

    payload = {
        "client_id": "pulse-mobile-app",
        "redirect_uri": "http://127.0.0.1:3000/callback",
        "response_type": "code",
        "scope": "openid profile",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": "mobile_state_456",
        "email": "developer@pulseauth.dev",
        "password": "DevPass2026!",
        "action": "approve",
    }
    resp = client.post("/oauth/authorize", json=payload)
    assert resp.status_code == 200
    data = resp.get_json()
    assert "code" in data
    assert "redirect_uri" in data
    assert "code=" in data["redirect_uri"]
    assert "state=mobile_state_456" in data["redirect_uri"]


def test_authorize_get_pre_authenticated_json_response(client, app, seeded_db):
    """Verify pre-authenticated user with consent gets JSON response if requested."""
    with app.app_context():
        conn = get_db()
        user = UserModel.get_by_email(conn, "developer@pulseauth.dev")
        ConsentModel.grant_consent(
            conn, user["id"], "pulse-web-app", ["openid", "profile"]
        )

    url = (
        f"/oauth/authorize?response_type=code"
        f"&client_id=pulse-web-app"
        f"&redirect_uri=http://127.0.0.1:3000/callback"
        f"&scope=openid%20profile"
        f"&state=direct_json"
        f"&user_id={user['id']}"
    )
    resp = client.get(url, headers={"Accept": "application/json"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert "code" in data
    assert "code=" in data["redirect_uri"]


def test_authorize_get_invalid_user_id_handled(client, seeded_db):
    """Verify invalid user_id query parameter does not crash the endpoint."""
    url = (
        "/oauth/authorize?response_type=code"
        "&client_id=pulse-web-app"
        "&redirect_uri=http://127.0.0.1:3000/callback"
        "&scope=openid"
        "&user_id=invalid_id"
    )
    resp = client.get(url, headers={"Accept": "application/json"})
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "consent_required"


def test_authorize_post_invalid_client_returns_400(client, seeded_db):
    """Verify POST /oauth/authorize with invalid client returns 400."""
    payload = {
        "client_id": "nonexistent-client",
        "redirect_uri": "http://127.0.0.1:3000/callback",
        "response_type": "code",
    }
    resp = client.post("/oauth/authorize", json=payload)
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "invalid_client"


def test_authorize_post_unsupported_response_type_redirects(client, seeded_db):
    """Verify POST /oauth/authorize with invalid response_type handles errors."""
    payload = {
        "client_id": "pulse-web-app",
        "redirect_uri": "http://127.0.0.1:3000/callback",
        "response_type": "invalid_type",
        "state": "post_state",
    }
    resp_json = client.post("/oauth/authorize", json=payload)
    assert resp_json.status_code == 400
    assert resp_json.get_json()["error"] == "unsupported_response_type"

    resp_form = client.post("/oauth/authorize", data=payload)
    assert resp_form.status_code == 302
    assert "error=unsupported_response_type" in resp_form.headers["Location"]


def test_authorize_post_deny_json_returns_200(client, seeded_db):
    """Verify JSON POST /oauth/authorize action=deny returns 200 and redirect_uri."""
    payload = {
        "client_id": "pulse-web-app",
        "redirect_uri": "http://127.0.0.1:3000/callback",
        "response_type": "code",
        "action": "deny",
        "state": "deny_json_state",
    }
    resp = client.post("/oauth/authorize", json=payload)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["error"] == "access_denied"
    assert "error=access_denied" in data["redirect_uri"]
