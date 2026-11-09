"""OpenID Connect Core 1.0 UserInfo endpoint."""

from typing import Any, Dict, List, Optional

from flask import Blueprint, Response, current_app, jsonify, request

from app.db.connection import get_db
from app.models.user_model import UserModel
from app.services.token_service import TokenService

userinfo_bp = Blueprint("userinfo", __name__)


def userinfo_error(
    code: str,
    description: str,
    status: int = 401,
    auth_header: Optional[str] = None,
) -> Response:
    """Build standard RFC 6750 Bearer token error response."""
    resp = jsonify({"error": code, "error_description": description})
    resp.status_code = status
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["Pragma"] = "no-cache"
    if auth_header:
        resp.headers["WWW-Authenticate"] = auth_header
    return resp


@userinfo_bp.route("/oauth/userinfo", methods=["GET", "POST"])
def userinfo_endpoint() -> Response:
    """Return verified identity claims for authenticated OpenID Connect users."""
    conn = get_db()
    rsa_manager = current_app.extensions["rsa_manager"]
    issuer = current_app.config.get("ISSUER", "http://127.0.0.1:5000")

    # 1. Extract Bearer token from Authorization header
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return userinfo_error(
            code="invalid_token",
            description="Missing or malformed Authorization header.",
            status=401,
            auth_header='Bearer error="invalid_token"',
        )

    raw_token = auth_header[7:].strip()
    if not raw_token:
        return userinfo_error(
            code="invalid_token",
            description="Empty Bearer token provided.",
            status=401,
            auth_header='Bearer error="invalid_token"',
        )

    # 2. Cryptographic and database verification
    valid, payload, db_record, err_msg = TokenService.verify_access_token(
        conn=conn,
        rsa_manager=rsa_manager,
        issuer=issuer,
        raw_token=raw_token,
    )
    if not valid or payload is None or db_record is None:
        return userinfo_error(
            code="invalid_token",
            description=err_msg,
            status=401,
            auth_header=f'Bearer error="invalid_token", error_description="{err_msg}"',
        )

    # 3. Scope validation (requires 'openid')
    token_scope = payload.get("scope", "")
    scopes_list: List[str] = token_scope.split() if token_scope else []
    if "openid" not in scopes_list:
        return userinfo_error(
            code="insufficient_scope",
            description="Access token is missing the required 'openid' scope.",
            status=403,
            auth_header=(
                'Bearer error="insufficient_scope", '
                'scope="openid", '
                'error_description="Requires openid scope"'
            ),
        )

    # 4. User identity validation
    user_id = db_record.get("user_id")
    if not user_id:
        return userinfo_error(
            code="forbidden",
            description="UserInfo is not available for machine-to-machine tokens.",
            status=403,
        )

    user = UserModel.get_by_id(conn, user_id)
    if not user:
        return userinfo_error(
            code="not_found",
            description="User profile not found.",
            status=404,
        )

    # 5. Assemble OIDC Claims
    claims: Dict[str, Any] = {
        "sub": str(user["id"]),
    }

    if "profile" in scopes_list:
        claims["name"] = user.get("full_name")
        email = user.get("email", "")
        if email and "@" in email:
            claims["preferred_username"] = email.split("@")[0]

    if "email" in scopes_list:
        claims["email"] = user.get("email")
        claims["email_verified"] = True

    resp = jsonify(claims)
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["Pragma"] = "no-cache"
    return resp
