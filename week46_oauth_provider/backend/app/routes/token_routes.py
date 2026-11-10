"""Token exchange endpoint implementing RFC 6749 and RFC 7636."""

from typing import Dict, List, Optional

from flask import Blueprint, Response, current_app, jsonify, request

from app.db.connection import get_db
from app.models.auth_code_model import AuthCodeModel
from app.models.client_model import ClientModel
from app.models.user_model import UserModel
from app.services.audit_service import AuditService
from app.services.client_auth_service import ClientAuthService
from app.services.pkce_service import PKCEService
from app.services.refresh_service import RefreshTokenService
from app.services.token_service import TokenService

token_bp = Blueprint("token", __name__)


def oauth_error(
    code: str,
    description: str,
    status: int = 400,
    headers: Optional[Dict[str, str]] = None,
) -> Response:
    """Build standard RFC 6749 Section 5.2 error response."""
    resp = jsonify({"error": code, "error_description": description})
    resp.status_code = status
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["Pragma"] = "no-cache"
    if headers:
        for k, v in headers.items():
            resp.headers[k] = v
    return resp


@token_bp.route("/oauth/token", methods=["POST"])
def token_endpoint() -> Response:
    """Handle OAuth 2.0 token requests for authorization_code and client_credentials."""
    conn = get_db()
    rsa_manager = current_app.extensions["rsa_manager"]
    issuer = current_app.config.get("ISSUER", "http://127.0.0.1:5000")

    # Extract parameters from form or JSON body
    data = request.form or request.get_json(silent=True) or {}
    grant_type = data.get("grant_type")

    if not grant_type:
        return oauth_error(
            "invalid_request", "Missing required 'grant_type' parameter."
        )

    # 1. Authorization Code Grant Flow
    if grant_type == "authorization_code":
        valid_auth, client, err_code, err_desc, status = ClientAuthService.authenticate(
            conn, request, allow_public=True
        )
        if not valid_auth or client is None:
            auth_headers = (
                {"WWW-Authenticate": 'Basic realm="PulseAuth"'}
                if status == 401
                else None
            )
            return oauth_error(err_code, err_desc, status=status, headers=auth_headers)

        if not ClientModel.validate_grant_type(
            conn, client["client_id"], "authorization_code"
        ):
            return oauth_error(
                "unauthorized_client",
                "Client is not authorized to use the authorization_code grant type.",
            )

        code = data.get("code")
        redirect_uri = data.get("redirect_uri")

        if not code:
            return oauth_error("invalid_request", "Missing 'code' parameter.")
        if not redirect_uri:
            return oauth_error("invalid_request", "Missing 'redirect_uri' parameter.")

        # Validate code record
        code_valid, code_rec, code_err = AuthCodeModel.validate_code(conn, code)
        if not code_valid or code_rec is None:
            AuditService.log(
                conn=conn,
                event_type="token_exchange_failed",
                status="failure",
                client_id=client["client_id"],
                ip_address=request.remote_addr,
                details={"reason": code_err},
            )
            return oauth_error("invalid_grant", code_err)

        # Verify client and redirect_uri match authorization record
        if code_rec["client_id"] != client["client_id"]:
            return oauth_error(
                "invalid_grant",
                "Authorization code was issued to a different client.",
            )

        if code_rec["redirect_uri"] != redirect_uri:
            return oauth_error(
                "invalid_grant",
                "redirect_uri does not match original authorization request.",
            )

        # PKCE Verification
        stored_challenge = code_rec.get("code_challenge")
        if stored_challenge:
            code_verifier = data.get("code_verifier")
            if not code_verifier:
                return oauth_error(
                    "invalid_grant",
                    "Missing 'code_verifier' for PKCE-protected authorization code.",
                )

            method = code_rec.get("code_challenge_method") or "S256"
            pkce_valid, pkce_err = PKCEService.verify(
                verifier=code_verifier, challenge=stored_challenge, method=method
            )
            if not pkce_valid:
                AuditService.log(
                    conn=conn,
                    event_type="pkce_verification_failed",
                    status="failure",
                    client_id=client["client_id"],
                    ip_address=request.remote_addr,
                    details={"error": pkce_err},
                )
                return oauth_error(
                    "invalid_grant", f"PKCE verification failed: {pkce_err}"
                )

        # Mark code as redeemed atomically
        if not AuthCodeModel.mark_used(conn, code):
            return oauth_error(
                "invalid_grant",
                "Authorization code has already been redeemed.",
            )

        # Fetch authenticated user
        user = UserModel.get_by_id(conn, code_rec["user_id"])
        if not user:
            return oauth_error("invalid_grant", "User associated with code not found.")

        # Issue tokens
        acc_ttl = current_app.config.get("ACCESS_TOKEN_TTL_SECONDS", 3600)
        id_ttl = current_app.config.get("ID_TOKEN_TTL_SECONDS", 3600)
        ref_ttl = current_app.config.get("REFRESH_TOKEN_TTL_SECONDS", 30 * 24 * 3600)

        tokens = TokenService.issue_tokens(
            conn=conn,
            rsa_manager=rsa_manager,
            issuer=issuer,
            client_id=client["client_id"],
            scope=code_rec["scope"],
            user=user,
            nonce=code_rec.get("nonce"),
            access_token_ttl=acc_ttl,
            id_token_ttl=id_ttl,
            refresh_token_ttl=ref_ttl,
        )

        AuditService.log(
            conn=conn,
            event_type="token_issued",
            status="success",
            client_id=client["client_id"],
            user_id=user["id"],
            ip_address=request.remote_addr,
            details={
                "grant_type": "authorization_code",
                "scope": code_rec["scope"],
            },
        )

        resp = jsonify(tokens)
        resp.headers["Cache-Control"] = "no-store"
        resp.headers["Pragma"] = "no-cache"
        return resp

    # 2. Client Credentials Grant Flow
    if grant_type == "client_credentials":
        valid_auth, client, err_code, err_desc, status = ClientAuthService.authenticate(
            conn, request, allow_public=False
        )
        if not valid_auth or client is None:
            auth_headers = (
                {"WWW-Authenticate": 'Basic realm="PulseAuth"'}
                if status == 401
                else None
            )
            return oauth_error(err_code, err_desc, status=status, headers=auth_headers)

        if not ClientModel.validate_grant_type(
            conn, client["client_id"], "client_credentials"
        ):
            return oauth_error(
                "unauthorized_client",
                "Client is not authorized to use the client_credentials grant type.",
            )

        requested_scope = data.get("scope")
        if requested_scope:
            scopes_list: List[str] = requested_scope.split()
            if not ClientModel.validate_scopes(conn, client["client_id"], scopes_list):
                return oauth_error(
                    "invalid_scope",
                    "Requested scope exceeds client allowed permissions.",
                )
            effective_scope = requested_scope
        else:
            effective_scope = " ".join(client.get("scopes", []))

        acc_ttl = current_app.config.get("ACCESS_TOKEN_TTL_SECONDS", 3600)
        tokens = TokenService.issue_tokens(
            conn=conn,
            rsa_manager=rsa_manager,
            issuer=issuer,
            client_id=client["client_id"],
            scope=effective_scope,
            user=None,
            access_token_ttl=acc_ttl,
        )

        AuditService.log(
            conn=conn,
            event_type="token_issued",
            status="success",
            client_id=client["client_id"],
            ip_address=request.remote_addr,
            details={
                "grant_type": "client_credentials",
                "scope": effective_scope,
            },
        )

        resp = jsonify(tokens)
        resp.headers["Cache-Control"] = "no-store"
        resp.headers["Pragma"] = "no-cache"
        return resp

    # 3. Refresh Token Grant Flow
    if grant_type == "refresh_token":
        valid_auth, client, err_code, err_desc, status = ClientAuthService.authenticate(
            conn, request, allow_public=True
        )
        if not valid_auth or client is None:
            auth_headers = (
                {"WWW-Authenticate": 'Basic realm="PulseAuth"'}
                if status == 401
                else None
            )
            return oauth_error(err_code, err_desc, status=status, headers=auth_headers)

        if not ClientModel.validate_grant_type(
            conn, client["client_id"], "refresh_token"
        ):
            return oauth_error(
                "unauthorized_client",
                "Client is not authorized to use the refresh_token grant type.",
            )

        refresh_token = data.get("refresh_token")
        if not refresh_token:
            return oauth_error(
                "invalid_request", "Missing required 'refresh_token' parameter."
            )

        requested_scope = data.get("scope")
        acc_ttl = current_app.config.get("ACCESS_TOKEN_TTL_SECONDS", 3600)
        id_ttl = current_app.config.get("ID_TOKEN_TTL_SECONDS", 3600)
        ref_ttl = current_app.config.get("REFRESH_TOKEN_TTL_SECONDS", 30 * 24 * 3600)

        success, new_tokens, code, desc, st = RefreshTokenService.rotate_token(
            conn=conn,
            rsa_manager=rsa_manager,
            issuer=issuer,
            client=client,
            refresh_token=refresh_token,
            requested_scope=requested_scope,
            ip_address=request.remote_addr,
            access_token_ttl=acc_ttl,
            id_token_ttl=id_ttl,
            refresh_token_ttl=ref_ttl,
        )

        if not success or new_tokens is None:
            return oauth_error(code, desc, status=st)

        resp = jsonify(new_tokens)
        resp.headers["Cache-Control"] = "no-store"
        resp.headers["Pragma"] = "no-cache"
        return resp

    # Unsupported grant type
    return oauth_error(
        "unsupported_grant_type", f"Unsupported grant_type: '{grant_type}'."
    )
