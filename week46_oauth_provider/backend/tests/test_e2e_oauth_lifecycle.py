"""Comprehensive End-to-End Lifecycle & Security Chaos Tests for PulseAuth."""

import base64
from typing import Dict

import jwt

from app.services.pkce_service import PKCEService


def test_e2e_full_authorization_code_pkce_oidc_lifecycle(client, seeded_db):
    """Test full journey: Register, PKCE, Authorize, Token, UserInfo, Revoke."""
    # Step 1: Register a new confidential client application
    reg_res = client.post(
        "/api/v1/clients",
        json={
            "client_name": "E2E Enterprise Web App",
            "client_type": "confidential",
            "redirect_uris": ["https://app.pulseauth.dev/oauth/callback"],
            "grant_types": ["authorization_code", "refresh_token"],
            "scopes": [
                "openid",
                "profile",
                "email",
                "offline_access",
                "read:documents",
                "write:documents",
            ],
        },
    )
    assert reg_res.status_code == 201
    client_data = reg_res.get_json()["data"]
    client_id = client_data["client_id"]
    client_secret = client_data["client_secret"]

    # Step 2: Authenticate user to obtain session subject ID
    login_res = client.post(
        "/api/v1/auth/login",
        json={
            "email": "developer@pulseauth.dev",
            "password": "DevPass2026!",
        },
    )
    assert login_res.status_code == 200
    user_id = login_res.get_json()["user"]["id"]

    # Step 3: Compute RFC 7636 PKCE S256 verifier and challenge
    code_verifier = PKCEService.generate_verifier(length=64)
    code_challenge = PKCEService.compute_challenge(code_verifier, "S256")

    # Step 4: Authorization Request & Consent
    auth_res = client.post(
        "/oauth/authorize",
        json={
            "client_id": client_id,
            "redirect_uri": "https://app.pulseauth.dev/oauth/callback",
            "response_type": "code",
            "scope": (
                "openid profile email offline_access read:documents write:documents"
            ),
            "state": "e2e_state_12345",
            "nonce": "e2e_nonce_67890",
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "email": "developer@pulseauth.dev",
            "password": "DevPass2026!",
            "action": "approve",
        },
    )
    assert auth_res.status_code == 200
    auth_data = auth_res.get_json()
    auth_code = auth_data["code"]

    # Step 5: Token Exchange via HTTP Basic client authentication
    basic_auth = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    token_res = client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": auth_code,
            "redirect_uri": "https://app.pulseauth.dev/oauth/callback",
            "code_verifier": code_verifier,
        },
        headers={"Authorization": f"Basic {basic_auth}"},
    )
    assert token_res.status_code == 200
    tokens = token_res.get_json()
    access_token = tokens["access_token"]
    id_token = tokens["id_token"]
    refresh_token = tokens["refresh_token"]
    assert tokens["token_type"] == "Bearer"

    # Step 6: Validate ID Token against public JWKS endpoint
    jwks_res = client.get("/.well-known/jwks.json")
    assert jwks_res.status_code == 200
    jwks = jwks_res.get_json()
    assert len(jwks["keys"]) > 0
    active_jwk = jwks["keys"][0]

    # Decode unverified to inspect header kid and claims
    id_header = jwt.get_unverified_header(id_token)
    assert id_header["alg"] == "RS256"
    assert id_header["kid"] == active_jwk["kid"]

    id_claims = jwt.decode(id_token, options={"verify_signature": False})
    assert id_claims["nonce"] == "e2e_nonce_67890"
    assert id_claims["email"] == "developer@pulseauth.dev"
    assert id_claims["aud"] == client_id

    # Step 7: Access OIDC UserInfo endpoint
    userinfo_res = client.get(
        "/oauth/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert userinfo_res.status_code == 200
    userinfo = userinfo_res.get_json()
    assert userinfo["email"] == "developer@pulseauth.dev"
    assert userinfo["sub"] == str(user_id)

    # Step 8: Access Protected Resource APIs
    profile_res = client.get(
        "/api/v1/resource/profile",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert profile_res.status_code == 200
    assert profile_res.get_json()["data"]["email"] == "developer@pulseauth.dev"

    create_doc_res = client.post(
        "/api/v1/resource/documents",
        json={"title": "E2E Architecture Blueprint"},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert create_doc_res.status_code == 201
    doc_id = create_doc_res.get_json()["data"]["id"]
    assert doc_id.startswith("doc-user-")

    get_docs_res = client.get(
        "/api/v1/resource/documents",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert get_docs_res.status_code == 200
    docs = get_docs_res.get_json()["data"]
    assert any(d["id"] == "doc-sec-001" for d in docs)

    # Step 9: Refresh Token Rotation (RTR)
    rotate_res = client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        },
    )
    assert rotate_res.status_code == 200
    rotated_tokens = rotate_res.get_json()
    new_access_token = rotated_tokens["access_token"]
    new_refresh_token = rotated_tokens["refresh_token"]
    assert new_access_token != access_token
    assert new_refresh_token != refresh_token

    # Step 10: Introspect new and old tokens
    introspect_active = client.post(
        "/oauth/introspect",
        data={"token": new_access_token},
        headers={"Authorization": f"Basic {basic_auth}"},
    )
    assert introspect_active.status_code == 200
    assert introspect_active.get_json()["active"] is True

    introspect_old = client.post(
        "/oauth/introspect",
        data={"token": refresh_token},
        headers={"Authorization": f"Basic {basic_auth}"},
    )
    assert introspect_old.status_code == 200
    assert introspect_old.get_json()["active"] is False

    # Step 11: Revoke the new refresh token (RFC 7009 cascade)
    revoke_res = client.post(
        "/oauth/revoke",
        data={"token": new_refresh_token, "token_type_hint": "refresh_token"},
        headers={"Authorization": f"Basic {basic_auth}"},
    )
    assert revoke_res.status_code == 200

    # Verify both new tokens are now revoked
    introspect_revoked_ref = client.post(
        "/oauth/introspect",
        data={"token": new_refresh_token},
        headers={"Authorization": f"Basic {basic_auth}"},
    )
    assert introspect_revoked_ref.get_json()["active"] is False

    introspect_revoked_acc = client.post(
        "/oauth/introspect",
        data={"token": new_access_token},
        headers={"Authorization": f"Basic {basic_auth}"},
    )
    assert introspect_revoked_acc.get_json()["active"] is False


def test_e2e_machine_to_machine_client_credentials_lifecycle(client, seeded_db):
    """Test M2M lifecycle: Client Credentials -> Protected API -> Forbidden UserInfo."""
    # Step 1: Request M2M token using pre-seeded daemon client
    token_res = client.post(
        "/oauth/token",
        data={
            "grant_type": "client_credentials",
            "client_id": "pulse-m2m-service",
            "client_secret": "pulse_m2m_secret_2026",
            "scope": "read:documents write:documents",
        },
    )
    assert token_res.status_code == 200
    tokens = token_res.get_json()
    access_token = tokens["access_token"]
    assert "id_token" not in tokens
    assert "refresh_token" not in tokens

    # Step 2: Access documents API successfully
    docs_res = client.get(
        "/api/v1/resource/documents",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert docs_res.status_code == 200

    # Step 3: Attempt to call UserInfo endpoint with service token -> HTTP 403 Forbidden
    userinfo_res = client.get(
        "/oauth/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert userinfo_res.status_code == 403
    assert userinfo_res.get_json()["error"] == "insufficient_scope"


def test_chaos_tampered_pkce_verifier(client, seeded_db):
    """Chaos test: Tampered PKCE verifier rejected with invalid_grant."""
    code_verifier = PKCEService.generate_verifier(length=64)
    code_challenge = PKCEService.compute_challenge(code_verifier, "S256")

    auth_res = client.post(
        "/oauth/authorize",
        json={
            "client_id": "pulse-mobile-app",
            "redirect_uri": "com.pulseauth.app://callback",
            "response_type": "code",
            "scope": "openid profile",
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "email": "developer@pulseauth.dev",
            "password": "DevPass2026!",
            "action": "approve",
        },
    )
    assert auth_res.status_code == 200
    auth_code = auth_res.get_json()["code"]

    # Exchange with modified/corrupted verifier
    tampered_verifier = code_verifier[:-4] + "XXXX"
    bad_res = client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": "pulse-mobile-app",
            "code": auth_code,
            "redirect_uri": "com.pulseauth.app://callback",
            "code_verifier": tampered_verifier,
        },
    )
    assert bad_res.status_code == 400
    assert bad_res.get_json()["error"] == "invalid_grant"


def test_chaos_replayed_authorization_code_attack(client, seeded_db):
    """Chaos test: Replay attack with single-use authorization code rejected."""
    code_verifier = PKCEService.generate_verifier(length=64)
    code_challenge = PKCEService.compute_challenge(code_verifier, "S256")

    auth_res = client.post(
        "/oauth/authorize",
        json={
            "client_id": "pulse-mobile-app",
            "redirect_uri": "com.pulseauth.app://callback",
            "response_type": "code",
            "scope": "openid",
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "email": "developer@pulseauth.dev",
            "password": "DevPass2026!",
            "action": "approve",
        },
    )
    auth_code = auth_res.get_json()["code"]

    token_payload: Dict[str, str] = {
        "grant_type": "authorization_code",
        "client_id": "pulse-mobile-app",
        "code": auth_code,
        "redirect_uri": "com.pulseauth.app://callback",
        "code_verifier": code_verifier,
    }

    # First exchange succeeds
    res1 = client.post("/oauth/token", data=token_payload)
    assert res1.status_code == 200

    # Second exchange (replay) is rejected
    res2 = client.post("/oauth/token", data=token_payload)
    assert res2.status_code == 400
    assert res2.get_json()["error"] == "invalid_grant"


def test_chaos_refresh_token_reuse_family_revocation_cascade(client, seeded_db):
    """Chaos test: Reusing an already-rotated token revokes token family."""
    # Step 1: Initial token acquisition
    code_verifier = PKCEService.generate_verifier(length=64)
    code_challenge = PKCEService.compute_challenge(code_verifier, "S256")

    auth_res = client.post(
        "/oauth/authorize",
        json={
            "client_id": "pulse-web-app",
            "redirect_uri": "http://127.0.0.1:3000/callback",
            "response_type": "code",
            "scope": "openid profile offline_access",
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "email": "developer@pulseauth.dev",
            "password": "DevPass2026!",
            "action": "approve",
        },
    )
    auth_code = auth_res.get_json()["code"]

    res_initial = client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": "pulse-web-app",
            "client_secret": "pulse_web_secret_2026",
            "code": auth_code,
            "redirect_uri": "http://127.0.0.1:3000/callback",
            "code_verifier": code_verifier,
        },
    )
    tokens_v1 = res_initial.get_json()
    refresh_v1 = tokens_v1["refresh_token"]

    # Step 2: Legitimate rotation from V1 -> V2
    res_rotate = client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "client_id": "pulse-web-app",
            "client_secret": "pulse_web_secret_2026",
            "refresh_token": refresh_v1,
        },
    )
    assert res_rotate.status_code == 200
    tokens_v2 = res_rotate.get_json()
    access_v2 = tokens_v2["access_token"]
    refresh_v2 = tokens_v2["refresh_token"]

    # Step 3: Attacker replays refresh_v1 (already rotated)
    replay_res = client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "client_id": "pulse-web-app",
            "client_secret": "pulse_web_secret_2026",
            "refresh_token": refresh_v1,
        },
    )
    assert replay_res.status_code == 400
    assert replay_res.get_json()["error"] == "invalid_grant"

    # Step 4: Verify the entire family (including V2) has been cascade-revoked!
    introspect_v2 = client.post(
        "/oauth/introspect",
        data={
            "token": access_v2,
            "client_id": "pulse-web-app",
            "client_secret": "pulse_web_secret_2026",
        },
    )
    assert introspect_v2.status_code == 200
    assert introspect_v2.get_json()["active"] is False

    introspect_v2_ref = client.post(
        "/oauth/introspect",
        data={
            "token": refresh_v2,
            "client_id": "pulse-web-app",
            "client_secret": "pulse_web_secret_2026",
        },
    )
    assert introspect_v2_ref.status_code == 200
    assert introspect_v2_ref.get_json()["active"] is False

    # Resource server rejects access_v2
    resource_res = client.get(
        "/api/v1/resource/profile",
        headers={"Authorization": f"Bearer {access_v2}"},
    )
    assert resource_res.status_code == 401


def test_chaos_tampered_jwt_signature(client, seeded_db):
    """Chaos test: Tampering with JWT signature causes immediate rejection."""
    # Obtain legitimate access token
    token_res = client.post(
        "/oauth/token",
        data={
            "grant_type": "client_credentials",
            "client_id": "pulse-m2m-service",
            "client_secret": "pulse_m2m_secret_2026",
            "scope": "read:documents",
        },
    )
    valid_token = token_res.get_json()["access_token"]

    # Verify legitimate token succeeds
    ok_res = client.get(
        "/api/v1/resource/documents",
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert ok_res.status_code == 200

    # Tamper with the cryptographic signature segment
    parts = valid_token.split(".")
    tampered_sig = parts[2][:-6] + "abcdef"
    tampered_token = f"{parts[0]}.{parts[1]}.{tampered_sig}"

    bad_res = client.get(
        "/api/v1/resource/documents",
        headers={"Authorization": f"Bearer {tampered_token}"},
    )
    assert bad_res.status_code == 401
    assert "invalid_token" in bad_res.headers.get("WWW-Authenticate", "")


def test_chaos_unregistered_redirect_uri_rejected(client, seeded_db):
    """Chaos test: Unregistered redirect URI rejected with HTTP 400."""
    auth_res = client.get(
        "/oauth/authorize?response_type=code"
        "&client_id=pulse-web-app"
        "&redirect_uri=https://evil-attacker.example.com/steal-code"
    )
    assert auth_res.status_code == 400
    assert auth_res.get_json()["error"] == "invalid_request"
