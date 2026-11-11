"""Token guard security middleware validating RS256 Bearer JWTs and scopes."""

from functools import wraps
from typing import Callable, List, Optional

from flask import current_app, jsonify, request

from app.db.connection import get_db
from app.models.user_model import UserModel
from app.services.token_service import TokenService


def require_oauth_token(
    required_scopes: Optional[List[str]] = None,
    any_of_scopes: Optional[List[str]] = None,
) -> Callable:
    """
    Decorator enforcing OAuth 2.0 Bearer token validation and scope authorization.

    Validates:
    1. Authorization header format (RFC 6750 Bearer)
    2. Cryptographic signature and issuer (RS256 JWT)
    3. Active database status and non-revocation
    4. Required scope subset inclusion and any-of scope matching
    """

    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            auth_header = request.headers.get("Authorization")
            if not auth_header:
                resp = jsonify(
                    {
                        "error": "invalid_token",
                        "error_description": "Missing Authorization header.",
                    }
                )
                resp.status_code = 401
                resp.headers["WWW-Authenticate"] = (
                    'Bearer error="invalid_token", '
                    'error_description="Missing Authorization header."'
                )
                return resp

            parts = auth_header.split(maxsplit=1)
            if len(parts) != 2 or parts[0].lower() != "bearer":
                resp = jsonify(
                    {
                        "error": "invalid_token",
                        "error_description": (
                            "Malformed Authorization header; expected Bearer token."
                        ),
                    }
                )
                resp.status_code = 401
                resp.headers["WWW-Authenticate"] = (
                    'Bearer error="invalid_token", '
                    'error_description="Malformed Authorization header."'
                )
                return resp

            raw_token = parts[1].strip()
            conn = get_db()
            rsa_manager = current_app.extensions["rsa_manager"]
            issuer = current_app.config.get("ISSUER", "http://127.0.0.1:5000")

            valid, payload, db_rec, err = TokenService.verify_access_token(
                conn=conn,
                rsa_manager=rsa_manager,
                issuer=issuer,
                raw_token=raw_token,
            )

            if not valid or payload is None:
                resp = jsonify(
                    {
                        "error": "invalid_token",
                        "error_description": err or "Invalid or expired access token.",
                    }
                )
                resp.status_code = 401
                resp.headers["WWW-Authenticate"] = (
                    f'Bearer error="invalid_token", error_description="{err}"'
                )
                return resp

            # Verify required scopes (all must be present)
            granted = set(payload.get("scope", "").split())
            if required_scopes:
                required = set(required_scopes)
                if not required.issubset(granted):
                    missing = required - granted
                    scope_str = " ".join(required_scopes)
                    desc = (
                        "Insufficient scope: missing " f"{', '.join(sorted(missing))}."
                    )
                    resp = jsonify(
                        {
                            "error": "insufficient_scope",
                            "error_description": desc,
                        }
                    )
                    resp.status_code = 403
                    resp.headers["WWW-Authenticate"] = (
                        f'Bearer error="insufficient_scope", scope="{scope_str}", '
                        f'error_description="{desc}"'
                    )
                    return resp

            # Verify any-of scopes (at least one must be present)
            if any_of_scopes:
                if not (set(any_of_scopes) & granted):
                    scope_str = " ".join(any_of_scopes)
                    desc = f"Insufficient scope: requires one of [{scope_str}]."
                    resp = jsonify(
                        {
                            "error": "insufficient_scope",
                            "error_description": desc,
                        }
                    )
                    resp.status_code = 403
                    resp.headers["WWW-Authenticate"] = (
                        f'Bearer error="insufficient_scope", scope="{scope_str}", '
                        f'error_description="{desc}"'
                    )
                    return resp

            # Attach identity and token context to request
            request.oauth_token = payload
            request.oauth_sub = payload.get("sub")
            request.oauth_client_id = payload.get("client_id")
            request.oauth_scopes = set(payload.get("scope", "").split())
            request.oauth_db_record = db_rec

            sub_val = payload.get("sub")
            if sub_val and sub_val.isdigit():
                request.oauth_user = UserModel.get_by_id(conn, int(sub_val))
            else:
                request.oauth_user = None

            return fn(*args, **kwargs)

        return wrapper

    return decorator
