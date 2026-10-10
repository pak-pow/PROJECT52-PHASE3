import hashlib
import hmac
import json
import time
from functools import wraps

from graphql import GraphQLError

# Secret key used for signing lightweight tokens
AUTH_SECRET_KEY = "pulsegraph-production-secret-token-key-2026"
TOKEN_EXPIRY_SECONDS = 86400 * 7  # 7 days


def generate_auth_token(user):
    """
    Generates a secure HMAC-SHA256 signed bearer token for a user record.
    """
    if not user or not user.get("id"):
        raise ValueError("Cannot generate auth token for invalid user.")

    payload = {
        "sub": int(user["id"]),
        "username": user["username"],
        "role": (user.get("role") or "DEVELOPER").upper(),
        "iat": int(time.time()),
        "exp": int(time.time()) + TOKEN_EXPIRY_SECONDS,
    }

    payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    signature = hmac.new(
        AUTH_SECRET_KEY.encode("utf-8"),
        payload_json.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    # Hex-encoded payload + signature
    payload_hex = payload_json.encode("utf-8").hex()
    return f"{payload_hex}.{signature}"


def decode_auth_token(token):
    """
    Validates and decodes a signed bearer token.
    Returns the user payload dict or None if invalid or expired.
    """
    if not token or "." not in token:
        return None

    try:
        parts = token.split(".", 1)
        if len(parts) != 2:
            return None

        payload_hex, signature = parts
        payload_json = bytes.fromhex(payload_hex).decode("utf-8")

        expected_sig = hmac.new(
            AUTH_SECRET_KEY.encode("utf-8"),
            payload_json.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(signature, expected_sig):
            return None

        payload = json.loads(payload_json)
        if payload.get("exp", 0) < time.time():
            return None

        return payload
    except Exception:
        return None


def get_current_user(info):
    """
    Extracts the authenticated user dict from GraphQL execution context.
    """
    if not info:
        return None
    ctx = getattr(info, "context", None)
    if isinstance(ctx, dict):
        return ctx.get("current_user")
    if hasattr(ctx, "current_user"):
        return getattr(ctx, "current_user")
    return None


def require_auth(fn):
    """
    Decorator requiring an authenticated user in GraphQL context.
    Raises GraphQLError if unauthenticated.
    """

    @wraps(fn)
    def wrapper(root, info, *args, **kwargs):
        current_user = get_current_user(info)
        if not current_user:
            raise GraphQLError("Authentication required to perform this operation.")
        return fn(root, info, *args, **kwargs)

    return wrapper


def require_role(allowed_roles):
    """
    Decorator requiring the authenticated user to hold one of the allowed roles.
    Raises GraphQLError if unauthorized.
    """
    roles_set = {r.upper() for r in allowed_roles}

    def decorator(fn):
        @wraps(fn)
        def wrapper(root, info, *args, **kwargs):
            current_user = get_current_user(info)
            if not current_user:
                raise GraphQLError("Authentication required to perform this operation.")

            user_role = (current_user.get("role") or "DEVELOPER").upper()
            if user_role not in roles_set:
                allowed_str = ", ".join(sorted(roles_set))
                raise GraphQLError(
                    f"Access denied: insufficient permissions. Required: {allowed_str}."
                )
            return fn(root, info, *args, **kwargs)

        return wrapper

    return decorator


def redact_email(email):
    """
    Partially redacts an email address for public unauthenticated views.
    Example: alex_chen@example.com -> a***n@example.com
    """
    if not email or "@" not in email:
        return "redacted@example.com"

    local, domain = email.split("@", 1)
    if len(local) <= 2:
        redacted_local = local[0] + "***"
    else:
        redacted_local = local[0] + "***" + local[-1]

    return f"{redacted_local}@{domain}"
