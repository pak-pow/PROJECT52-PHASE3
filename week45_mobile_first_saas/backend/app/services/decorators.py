"""Route gatekeeping decorators for feature entitlements and quota enforcement."""

from functools import wraps
from typing import Callable

from flask import current_app, jsonify, make_response, request

from app.config.settings import Config
from app.db.connection import get_db_connection
from app.services.auth_service import verify_auth_token
from app.services.entitlements_service import EntitlementsService
from app.services.usage_service import UsageService


def _resolve_user_id() -> str:
    """Extract authenticated user identifier from headers, query parameters, or body."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        secret = current_app.config.get("SECRET_KEY", Config.SECRET_KEY)
        payload = verify_auth_token(token, secret_key=secret)
        if payload and payload.get("user_id"):
            return str(payload["user_id"])

    user_id = request.headers.get("X-User-ID")
    if user_id:
        return user_id

    user_id = request.args.get("user_id")
    if user_id:
        return user_id

    if request.is_json and isinstance(request.json, dict):
        user_id = request.json.get("user_id")
        if user_id:
            return str(user_id)

    # Default to seeded demo user if unspecified
    return "usr_demo_alice"


def require_entitlement(feature_key: str) -> Callable:
    """Route decorator blocking requests if user's tier lacks specified feature flag."""

    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def decorated_function(*args, **kwargs):
            db_path = current_app.config.get("DB_PATH", Config.DB_PATH)
            conn = get_db_connection(db_path)
            try:
                entitlements = EntitlementsService(conn)
                user_id = _resolve_user_id()
                has_access = entitlements.check_feature_access(
                    user_id=user_id, feature_key=feature_key
                )

                if not has_access:
                    return (
                        jsonify(
                            {
                                "error": "feature_not_entitled",
                                "message": (
                                    f"Your plan tier does not include "
                                    f"the '{feature_key}' feature."
                                ),
                                "feature": feature_key,
                                "user_id": user_id,
                                "upgrade_url": "/#plans",
                            }
                        ),
                        403,
                    )
            finally:
                conn.close()

            return f(*args, **kwargs)

        return decorated_function

    return decorator


def check_quota(
    metric_key: str,
    cost: int = 1,
    record: bool = True,
) -> Callable:
    """Route decorator enforcing quantitative limits and recording metered usage."""

    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def decorated_function(*args, **kwargs):
            db_path = current_app.config.get("DB_PATH", Config.DB_PATH)
            conn = get_db_connection(db_path)
            try:
                usage_service = UsageService(conn)
                entitlements = EntitlementsService(conn, usage_service=usage_service)
                user_id = _resolve_user_id()

                can_consume, status_data = entitlements.can_consume_metric(
                    user_id=user_id,
                    metric_key=metric_key,
                    requested_units=cost,
                )

                if not can_consume:
                    return (
                        jsonify(
                            {
                                "error": "quota_exceeded",
                                "message": (
                                    f"Quota limit exceeded for '{metric_key}'."
                                ),
                                "metric": metric_key,
                                "current_usage": status_data["usage"],
                                "limit": status_data["limit"],
                                "requested": cost,
                                "upgrade_url": "/#plans",
                            }
                        ),
                        402,
                    )

                # Record consumption if permitted and requested
                if record:
                    active_sub = entitlements.get_active_subscription(user_id)
                    sub_id = active_sub.id if active_sub else None
                    usage_service.record_usage(
                        user_id=user_id,
                        metric_key=metric_key,
                        quantity=cost,
                        subscription_id=sub_id,
                    )
                    # Update status for header injection
                    status_data = usage_service.evaluate_quota_status(
                        current_usage=status_data["usage"] + cost,
                        limit=status_data["limit"],
                    )
            finally:
                conn.close()

            # Execute underlying endpoint
            response = make_response(f(*args, **kwargs))

            # Inject quota transparency headers
            response.headers["X-Quota-Limit"] = str(status_data["limit"])
            response.headers["X-Quota-Remaining"] = str(status_data["remaining"])
            response.headers["X-Quota-Used"] = str(status_data["usage"])
            if status_data.get("threshold_alert"):
                response.headers["X-Quota-Alert"] = status_data["threshold_alert"]

            return response

        return decorated_function

    return decorator
