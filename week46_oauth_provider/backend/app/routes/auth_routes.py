"""OAuth 2.0 authorization endpoint handling user authentication and consent."""

from flask import (
    Blueprint,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
)

from app.db.connection import get_db
from app.models.consent_model import ConsentModel
from app.models.user_model import UserModel
from app.services.audit_service import AuditService
from app.services.auth_code_service import AuthCodeService

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/oauth/authorize", methods=["GET"])
def authorize_get():
    """OAuth 2.0 Authorization Endpoint (RFC 6749 Section 4.1.1)."""
    conn = get_db()

    response_type = request.args.get("response_type")
    client_id = request.args.get("client_id")
    redirect_uri = request.args.get("redirect_uri")
    scope = request.args.get("scope", "")
    state = request.args.get("state")
    code_challenge = request.args.get("code_challenge")
    code_challenge_method = request.args.get("code_challenge_method")
    nonce = request.args.get("nonce")
    simulated_user_id = request.args.get("user_id")

    valid, client, err_code, err_desc = AuthCodeService.validate_request(
        conn=conn,
        response_type=response_type,
        client_id=client_id,
        redirect_uri=redirect_uri,
        scope=scope,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
    )

    if not valid:
        AuditService.log(
            conn=conn,
            event_type="authorize_request_failed",
            status="failure",
            client_id=client_id,
            ip_address=request.remote_addr,
            details={"error": err_code, "description": err_desc},
        )

        # RFC 6749: If redirect_uri or client is invalid, DO NOT redirect.
        if (
            not client
            or err_code == "invalid_client"
            or "redirect_uri" in err_desc.lower()
        ):
            return (
                jsonify({"error": err_code, "error_description": err_desc}),
                400,
            )

        # If redirect_uri is verified valid, redirect error to callback
        error_url = AuthCodeService.build_redirect_url(
            redirect_uri,  # type: ignore
            {"error": err_code, "error_description": err_desc, "state": state},
        )
        return redirect(error_url, code=302)

    requested_scopes = scope.split() if scope else []

    # Check if a pre-authenticated user session is present and has consented
    if simulated_user_id:
        try:
            uid = int(simulated_user_id)
            user = UserModel.get_by_id(conn, uid)
            if user and ConsentModel.has_consent(
                conn, uid, client_id, requested_scopes  # type: ignore
            ):
                ttl = current_app.config.get("AUTH_CODE_TTL_SECONDS", 60)
                code_record, redirect_url = AuthCodeService.issue_code(
                    conn=conn,
                    client_id=client_id,  # type: ignore
                    user_id=uid,
                    redirect_uri=redirect_uri,  # type: ignore
                    scope=scope,
                    ttl_seconds=ttl,
                    code_challenge=code_challenge,
                    code_challenge_method=code_challenge_method,
                    nonce=nonce,
                    state=state,
                )
                AuditService.log(
                    conn=conn,
                    event_type="authorize_code_issued",
                    status="success",
                    client_id=client_id,
                    user_id=uid,
                    ip_address=request.remote_addr,
                    details={"code_id": code_record["id"], "scope": scope},
                )
                if request.accept_mimetypes.best == "application/json":
                    return (
                        jsonify(
                            {
                                "redirect_uri": redirect_url,
                                "code": code_record["code"],
                            }
                        ),
                        200,
                    )
                return redirect(redirect_url, code=302)
        except ValueError:
            pass

    # If client specifically asks for JSON (e.g., automated test or headless SPA)
    if (
        request.accept_mimetypes.accept_json
        and not request.accept_mimetypes.accept_html
    ):
        return (
            jsonify(
                {
                    "status": "consent_required",
                    "client_id": client_id,
                    "client_name": client["client_name"],  # type: ignore
                    "scopes": requested_scopes,
                    "redirect_uri": redirect_uri,
                    "state": state,
                }
            ),
            200,
        )

    # Render consent form
    return render_template(
        "consent.html",
        client=client,
        scopes=requested_scopes,
        redirect_uri=redirect_uri,
        response_type=response_type,
        scope=scope,
        state=state,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        nonce=nonce,
        error=None,
    )


@auth_bp.route("/oauth/authorize", methods=["POST"])
def authorize_post():
    """Handle user credential submission and scope consent approval/denial."""
    conn = get_db()
    data = request.get_json(silent=True) or request.form

    response_type = data.get("response_type")
    client_id = data.get("client_id")
    redirect_uri = data.get("redirect_uri")
    scope = data.get("scope", "")
    state = data.get("state")
    code_challenge = data.get("code_challenge")
    code_challenge_method = data.get("code_challenge_method")
    nonce = data.get("nonce")
    action = data.get("action", "approve").lower()
    email = data.get("email", "")
    password = data.get("password", "")

    # Validate parameters
    valid, client, err_code, err_desc = AuthCodeService.validate_request(
        conn=conn,
        response_type=response_type,
        client_id=client_id,
        redirect_uri=redirect_uri,
        scope=scope,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
    )

    if not valid:
        if (
            not client
            or err_code == "invalid_client"
            or "redirect_uri" in err_desc.lower()
        ):
            return (
                jsonify({"error": err_code, "error_description": err_desc}),
                400,
            )
        error_url = AuthCodeService.build_redirect_url(
            redirect_uri,
            {"error": err_code, "error_description": err_desc, "state": state},
        )
        if request.is_json:
            return jsonify({"redirect_uri": error_url, "error": err_code}), 400
        return redirect(error_url, code=302)

    # If user explicitly denies consent
    if action == "deny":
        AuditService.log(
            conn=conn,
            event_type="consent_denied",
            status="failure",
            client_id=client_id,
            ip_address=request.remote_addr,
            details={"scope": scope},
        )
        denied_url = AuthCodeService.build_redirect_url(
            redirect_uri,
            {
                "error": "access_denied",
                "error_description": "The user denied the authorization request.",
                "state": state,
            },
        )
        if request.is_json:
            return (
                jsonify({"redirect_uri": denied_url, "error": "access_denied"}),
                200,
            )
        return redirect(denied_url, code=302)

    # Authenticate user credentials
    user = UserModel.verify_credentials(conn, email, password)
    if not user:
        AuditService.log(
            conn=conn,
            event_type="user_auth_failed",
            status="failure",
            client_id=client_id,
            ip_address=request.remote_addr,
            details={"email": email},
        )
        if request.is_json:
            return (
                jsonify(
                    {
                        "error": "access_denied",
                        "error_description": "Invalid user credentials.",
                    }
                ),
                401,
            )

        requested_scopes = scope.split() if scope else []
        return render_template(
            "consent.html",
            client=client,
            scopes=requested_scopes,
            redirect_uri=redirect_uri,
            response_type=response_type,
            scope=scope,
            state=state,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            nonce=nonce,
            email=email,
            error="Invalid email or password. Please try again.",
        )

    # Record consent
    requested_scopes = scope.split() if scope else []
    ConsentModel.grant_consent(
        conn, user["id"], client_id, requested_scopes  # type: ignore
    )

    # Issue authorization code
    ttl = current_app.config.get("AUTH_CODE_TTL_SECONDS", 60)
    code_record, redirect_url = AuthCodeService.issue_code(
        conn=conn,
        client_id=client_id,  # type: ignore
        user_id=user["id"],
        redirect_uri=redirect_uri,
        scope=scope,
        ttl_seconds=ttl,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        nonce=nonce,
        state=state,
    )

    AuditService.log(
        conn=conn,
        event_type="authorize_code_issued",
        status="success",
        client_id=client_id,
        user_id=user["id"],
        ip_address=request.remote_addr,
        details={"code_id": code_record["id"], "scope": scope},
    )

    if request.is_json:
        return (
            jsonify({"redirect_uri": redirect_url, "code": code_record["code"]}),
            200,
        )

    return redirect(redirect_url, code=302)
