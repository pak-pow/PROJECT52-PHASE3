"""OpenID Connect RP-Initiated Logout 1.0 endpoint for PulseAuth."""

from typing import Any, Dict, Optional

import jwt
from flask import (
    Blueprint,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
)

from app.db.connection import get_db
from app.models.client_model import ClientModel
from app.models.token_model import TokenModel
from app.models.user_model import UserModel
from app.services.audit_service import AuditService
from app.services.auth_code_service import AuthCodeService

logout_bp = Blueprint("logout", __name__)


def _extract_hint_claims(
    rsa_manager: Any, id_token_hint: str
) -> Optional[Dict[str, Any]]:
    """Verify and extract claims from an id_token_hint JWT."""
    try:
        claims = rsa_manager.verify_jwt(id_token_hint)
        return claims
    except (jwt.PyJWTError, Exception):
        return None


@logout_bp.route("/oauth/logout", methods=["GET", "POST"])
def logout():
    """Handle OpenID Connect RP-Initiated Logout 1.0 requests."""
    conn = get_db()
    rsa_manager = current_app.extensions["rsa_manager"]

    # Support form, JSON, and query parameters
    params = request.values or (request.get_json(silent=True) or {})
    id_token_hint = params.get("id_token_hint")
    client_id = params.get("client_id")
    post_logout_redirect_uri = params.get("post_logout_redirect_uri")
    state = params.get("state")
    confirm = params.get("confirm", "").lower() in ("true", "1", "yes")

    hint_claims: Optional[Dict[str, Any]] = None
    if id_token_hint:
        hint_claims = _extract_hint_claims(rsa_manager, id_token_hint)
        if not hint_claims:
            return (
                jsonify(
                    {
                        "error": "invalid_request",
                        "error_description": "Invalid or tampered id_token_hint.",
                    }
                ),
                400,
            )

        aud = hint_claims.get("aud")
        hint_client_id = aud[0] if isinstance(aud, list) and aud else aud
        if client_id and hint_client_id and client_id != hint_client_id:
            return (
                jsonify(
                    {
                        "error": "invalid_request",
                        "error_description": (
                            "client_id does not match id_token_hint audience."
                        ),
                    }
                ),
                400,
            )
        if not client_id and hint_client_id:
            client_id = str(hint_client_id)

    # Validate client and post_logout_redirect_uri if supplied
    client = None
    if client_id:
        client = ClientModel.get_by_client_id(conn, client_id)

    if post_logout_redirect_uri:
        if not client:
            return (
                jsonify(
                    {
                        "error": "invalid_request",
                        "error_description": (
                            "Cannot validate post_logout_redirect_uri without client."
                        ),
                    }
                ),
                400,
            )

        registered_uris = client.get("redirect_uris", [])
        if post_logout_redirect_uri not in registered_uris:
            return (
                jsonify(
                    {
                        "error": "invalid_request",
                        "error_description": (
                            f"Unregistered post_logout_redirect_uri: "
                            f"{post_logout_redirect_uri}."
                        ),
                    }
                ),
                400,
            )

    # Resolve user
    user = None
    user_id = None
    if hint_claims and hint_claims.get("sub"):
        sub_str = str(hint_claims["sub"])
        if sub_str.isdigit():
            user_id = int(sub_str)
            user = UserModel.get_by_id(conn, user_id)

    # Determine confirmation state
    is_confirmed = confirm or request.method == "POST"

    # If GET and not confirmed and browser HTML requested, render confirmation
    is_json = request.is_json or (
        request.accept_mimetypes.accept_json
        and not request.accept_mimetypes.accept_html
    )

    if not is_confirmed and not is_json:
        return render_template(
            "logout.html",
            user=user,
            client=client,
            id_token_hint=id_token_hint,
            client_id=client_id,
            post_logout_redirect_uri=post_logout_redirect_uri,
            state=state,
            completed=False,
        )

    # Execute logout and token revocation
    if user_id:
        revoked_count = TokenModel.revoke_user_tokens(conn, user_id, client_id)
        AuditService.log(
            conn=conn,
            event_type="rp_logout_executed",
            status="success",
            client_id=client_id,
            user_id=user_id,
            ip_address=request.remote_addr,
            details={
                "revoked_count": revoked_count,
                "post_logout_redirect_uri": post_logout_redirect_uri,
            },
        )

    # Handle post-logout redirection or response
    if post_logout_redirect_uri:
        redirect_params: Dict[str, Any] = {}
        if state:
            redirect_params["state"] = state
        redirect_url = AuthCodeService.build_redirect_url(
            post_logout_redirect_uri, redirect_params
        )

        if is_json:
            return jsonify({"status": "logged_out", "redirect_uri": redirect_url}), 200
        return redirect(redirect_url, code=302)

    if is_json:
        return (
            jsonify(
                {
                    "status": "logged_out",
                    "message": "Successfully logged out from PulseAuth.",
                }
            ),
            200,
        )

    return render_template(
        "logout.html",
        user=user,
        client=client,
        completed=True,
    )
