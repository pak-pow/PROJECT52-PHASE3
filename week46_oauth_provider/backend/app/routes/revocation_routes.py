"""Token revocation endpoint implementing RFC 7009."""

from typing import Dict, Optional

from flask import Blueprint, Response, jsonify, request

from app.db.connection import get_db
from app.models.token_model import TokenModel
from app.services.audit_service import AuditService
from app.services.client_auth_service import ClientAuthService

revocation_bp = Blueprint("revocation", __name__)


def revocation_error(
    code: str,
    description: str,
    status: int = 400,
    headers: Optional[Dict[str, str]] = None,
) -> Response:
    """Build standard RFC 7009 error response."""
    resp = jsonify({"error": code, "error_description": description})
    resp.status_code = status
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["Pragma"] = "no-cache"
    if headers:
        for k, v in headers.items():
            resp.headers[k] = v
    return resp


@revocation_bp.route("/oauth/revoke", methods=["POST"])
def revoke_endpoint() -> Response:
    """
    Revoke an active access or refresh token per RFC 7009.

    Validates client authentication, verifies token ownership, and invalidates
    token or token family. Always returns HTTP 200 for invalid/unowned tokens
    to prevent information disclosure.
    """
    conn = get_db()
    data = request.form or request.get_json(silent=True) or {}

    # 1. Authenticate client (public or confidential)
    valid_auth, client, err_code, err_desc, status = ClientAuthService.authenticate(
        conn, request, allow_public=True
    )
    if not valid_auth or client is None:
        auth_headers = (
            {"WWW-Authenticate": 'Basic realm="PulseAuth"'} if status == 401 else None
        )
        return revocation_error(err_code, err_desc, status=status, headers=auth_headers)

    # 2. Extract token parameter
    token = data.get("token")
    if not token:
        return revocation_error(
            "invalid_request", "Missing required 'token' parameter."
        )

    token_type_hint = data.get("token_type_hint")

    # 3. Lookup token in persistence layer
    record = TokenModel.get_by_raw_token(conn, token)
    if record:
        # Check ownership: RFC 7009 Section 2.1
        if record["client_id"] != client["client_id"]:
            AuditService.log(
                conn=conn,
                event_type="token_revocation_ignored",
                status="failure",
                client_id=client["client_id"],
                ip_address=request.remote_addr,
                details={"reason": "Token was issued to a different client"},
            )
            # Must return 200 without revoking
            resp = jsonify({"status": "revoked"})
            resp.headers["Cache-Control"] = "no-store"
            resp.headers["Pragma"] = "no-cache"
            return resp

        # Revoke token
        if record.get("token_type") == "refresh_token":
            family_id = record.get("token_family_id")
            TokenModel.revoke_family(conn, family_id)
        else:
            TokenModel.revoke_by_hash(conn, record["token_value_hash"])

        AuditService.log(
            conn=conn,
            event_type="token_revoked",
            status="success",
            client_id=client["client_id"],
            user_id=record.get("user_id"),
            ip_address=request.remote_addr,
            details={
                "token_type": record.get("token_type"),
                "token_type_hint": token_type_hint,
                "family_id": record.get("token_family_id"),
            },
        )

    # Per RFC 7009 Section 2.2, return 200 OK
    resp = jsonify({"status": "revoked"})
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["Pragma"] = "no-cache"
    return resp
