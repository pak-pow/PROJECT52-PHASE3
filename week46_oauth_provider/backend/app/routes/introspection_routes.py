"""Token introspection endpoint implementing RFC 7662."""

from datetime import datetime, timezone
from typing import Dict, Optional

from flask import Blueprint, Response, current_app, jsonify, request

from app.db.connection import get_db
from app.models.token_model import TokenModel
from app.services.audit_service import AuditService
from app.services.client_auth_service import ClientAuthService

introspection_bp = Blueprint("introspection", __name__)


def introspection_error(
    code: str,
    description: str,
    status: int = 400,
    headers: Optional[Dict[str, str]] = None,
) -> Response:
    """Build standard RFC 7662 error response."""
    resp = jsonify({"error": code, "error_description": description})
    resp.status_code = status
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["Pragma"] = "no-cache"
    if headers:
        for k, v in headers.items():
            resp.headers[k] = v
    return resp


@introspection_bp.route("/oauth/introspect", methods=["POST"])
def introspect_endpoint() -> Response:
    """
    Introspect token metadata and active status per RFC 7662.

    Requires confidential client or resource server authentication.
    Returns active=True with metadata if token is valid, or active=False
    if token is invalid, revoked, or expired.
    """
    conn = get_db()
    data = request.form or request.get_json(silent=True) or {}

    # 1. Authenticate client (must be confidential / authenticated resource server)
    valid_auth, client, err_code, err_desc, status = ClientAuthService.authenticate(
        conn, request, allow_public=False
    )
    if not valid_auth or client is None:
        auth_headers = (
            {"WWW-Authenticate": 'Basic realm="PulseAuth"'} if status == 401 else None
        )
        return introspection_error(
            err_code, err_desc, status=status, headers=auth_headers
        )

    # 2. Extract token parameter
    token = data.get("token")
    if not token:
        return introspection_error(
            "invalid_request", "Missing required 'token' parameter."
        )

    # 3. Lookup token
    record = TokenModel.get_by_raw_token(conn, token)
    if not record:
        resp = jsonify({"active": False})
        resp.headers["Cache-Control"] = "no-store"
        resp.headers["Pragma"] = "no-cache"
        return resp

    # 4. Check revocation status
    if record.get("revoked_at") is not None:
        resp = jsonify({"active": False})
        resp.headers["Cache-Control"] = "no-store"
        resp.headers["Pragma"] = "no-cache"
        return resp

    # 5. Check expiration
    expires_at = TokenModel.parse_datetime(record.get("expires_at"))
    if expires_at and datetime.now(timezone.utc) > expires_at:
        resp = jsonify({"active": False})
        resp.headers["Cache-Control"] = "no-store"
        resp.headers["Pragma"] = "no-cache"
        return resp

    # 6. Build active token metadata
    issuer = current_app.config.get("ISSUER", "http://127.0.0.1:5000")
    exp_ts = int(expires_at.timestamp()) if expires_at else None
    created_at = TokenModel.parse_datetime(record.get("created_at"))
    iat_ts = int(created_at.timestamp()) if created_at else None

    sub = (
        str(record["user_id"])
        if record.get("user_id") is not None
        else record["client_id"]
    )

    payload = {
        "active": True,
        "scope": record.get("scope", ""),
        "client_id": record["client_id"],
        "sub": sub,
        "token_type": "Bearer",
        "exp": exp_ts,
        "iat": iat_ts,
        "iss": issuer,
    }

    if record.get("jti"):
        payload["jti"] = record["jti"]
    if record.get("token_type"):
        payload["token_type_hint"] = record["token_type"]

    AuditService.log(
        conn=conn,
        event_type="token_introspected",
        status="success",
        client_id=client["client_id"],
        user_id=record.get("user_id"),
        ip_address=request.remote_addr,
        details={
            "token_type": record.get("token_type"),
            "target_client_id": record["client_id"],
        },
    )

    resp = jsonify(payload)
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["Pragma"] = "no-cache"
    return resp
