"""Tests for @require_oauth_token security decorator and scope gatekeeper."""

from flask import jsonify

from app.db.connection import get_db
from app.models.token_model import TokenModel
from app.models.user_model import UserModel
from app.services.token_guard import require_oauth_token
from app.services.token_service import TokenService


def test_token_guard_missing_and_malformed_headers(app):
    """Verify 401 responses for missing or malformed Authorization headers."""

    # Register temporary test endpoint
    @app.route("/test-guard-missing", methods=["GET"])
    @require_oauth_token(required_scopes=["read:test"])
    def dummy_route():
        return jsonify({"status": "ok"}), 200

    client = app.test_client()

    # 1. Missing Authorization header
    resp_missing = client.get("/test-guard-missing")
    assert resp_missing.status_code == 401
    assert "WWW-Authenticate" in resp_missing.headers
    assert resp_missing.get_json()["error"] == "invalid_token"

    # 2. Malformed Authorization header (Basic instead of Bearer)
    resp_basic = client.get(
        "/test-guard-missing",
        headers={"Authorization": "Basic dXNlcjpwYXNz"},
    )
    assert resp_basic.status_code == 401
    assert "Malformed" in resp_basic.get_json()["error_description"]

    # 3. Empty Bearer header
    resp_empty = client.get(
        "/test-guard-missing",
        headers={"Authorization": "Bearer"},
    )
    assert resp_empty.status_code == 401


def test_token_guard_valid_token_and_scope_enforcement(app, seeded_db):
    """Verify successful access and scope validation with @require_oauth_token."""

    @app.route("/test-guard-scopes", methods=["GET"])
    @require_oauth_token(required_scopes=["read:documents", "write:documents"])
    def protected_dual_scope():
        return jsonify({"status": "authorized"}), 200

    @app.route("/test-guard-any-scope", methods=["GET"])
    @require_oauth_token(any_of_scopes=["profile", "read:profile"])
    def protected_any_scope():
        return jsonify({"status": "any_authorized"}), 200

    client = app.test_client()

    with app.app_context():
        conn = get_db()
        rsa = app.extensions["rsa_manager"]
        user = UserModel.get_by_id(conn, 1)

        # Token with full scopes
        bundle_full = TokenService.issue_tokens(
            conn=conn,
            rsa_manager=rsa,
            issuer="http://127.0.0.1:5000",
            client_id="pulse-web-app",
            scope="openid profile read:documents write:documents",
            user=user,
        )

        # Token with partial scopes (missing write:documents)
        bundle_partial = TokenService.issue_tokens(
            conn=conn,
            rsa_manager=rsa,
            issuer="http://127.0.0.1:5000",
            client_id="pulse-web-app",
            scope="openid read:documents",
            user=user,
        )

    token_full = bundle_full["access_token"]
    token_partial = bundle_partial["access_token"]

    # Full scopes succeed
    resp_ok = client.get(
        "/test-guard-scopes",
        headers={"Authorization": f"Bearer {token_full}"},
    )
    assert resp_ok.status_code == 200
    assert resp_ok.get_json()["status"] == "authorized"

    # Partial scope rejected with 403 Forbidden
    resp_forbidden = client.get(
        "/test-guard-scopes",
        headers={"Authorization": f"Bearer {token_partial}"},
    )
    assert resp_forbidden.status_code == 403
    assert resp_forbidden.get_json()["error"] == "insufficient_scope"
    assert "write:documents" in resp_forbidden.get_json()["error_description"]

    # any_of_scopes check
    resp_any_ok = client.get(
        "/test-guard-any-scope",
        headers={"Authorization": f"Bearer {token_full}"},
    )
    assert resp_any_ok.status_code == 200

    resp_any_fail = client.get(
        "/test-guard-any-scope",
        headers={"Authorization": f"Bearer {token_partial}"},
    )
    assert resp_any_fail.status_code == 403


def test_token_guard_revoked_and_expired_tokens(app, seeded_db):
    """Verify revoked or expired tokens are rejected by middleware."""

    @app.route("/test-guard-revocation", methods=["GET"])
    @require_oauth_token(required_scopes=["openid"])
    def protected_endpoint():
        return jsonify({"status": "ok"}), 200

    client = app.test_client()

    with app.app_context():
        conn = get_db()
        rsa = app.extensions["rsa_manager"]
        user = UserModel.get_by_id(conn, 1)

        bundle = TokenService.issue_tokens(
            conn=conn,
            rsa_manager=rsa,
            issuer="http://127.0.0.1:5000",
            client_id="pulse-web-app",
            scope="openid",
            user=user,
        )
        token = bundle["access_token"]

        # Revoke the token
        TokenModel.revoke(conn, token)

    resp_revoked = client.get(
        "/test-guard-revocation",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_revoked.status_code == 401
    assert "revoked" in resp_revoked.get_json()["error_description"].lower()
