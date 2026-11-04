"""Metered resource consumption tracking and quota summary routes."""

from flask import Blueprint, current_app, jsonify, make_response, request

from app.config.settings import Config
from app.db.connection import get_db_connection
from app.services.decorators import _resolve_user_id
from app.services.entitlements_service import EntitlementsService
from app.services.usage_service import UsageService

usage_bp = Blueprint("usage", __name__, url_prefix="/api/v1/usage")


@usage_bp.route("/record", methods=["POST"])
def record_usage():
    """Record discrete resource consumption with idempotency and quota headers."""
    user_id = _resolve_user_id()
    payload = request.get_json(silent=True) or {}
    metric_key = payload.get("metric_key", "").strip()
    quantity = payload.get("quantity", 1)
    idempotency_key = payload.get("idempotency_key")

    if not metric_key:
        return (
            jsonify(
                {
                    "error": "invalid_payload",
                    "message": "Field 'metric_key' is required.",
                }
            ),
            400,
        )

    try:
        quantity_int = int(quantity)
        if quantity_int <= 0:
            raise ValueError()
    except (ValueError, TypeError):
        return (
            jsonify(
                {
                    "error": "invalid_quantity",
                    "message": "Field 'quantity' must be a strictly positive integer.",
                }
            ),
            400,
        )

    db_path = current_app.config.get("DB_PATH", Config.DB_PATH)
    conn = get_db_connection(db_path)
    try:
        usage_service = UsageService(conn)
        entitlements_service = EntitlementsService(conn, usage_service=usage_service)
        sub = entitlements_service.get_active_subscription(user_id)
        sub_id = sub.id if sub else None

        record = usage_service.record_usage(
            user_id=user_id,
            metric_key=metric_key,
            quantity=quantity_int,
            subscription_id=sub_id,
            idempotency_key=idempotency_key,
        )

        _, status_data = entitlements_service.can_consume_metric(
            user_id=user_id,
            metric_key=metric_key,
            requested_units=0,
        )

        response = make_response(
            jsonify(
                {
                    "record": record.to_dict(),
                    "quota_status": status_data,
                    "message": "Usage recorded successfully.",
                }
            ),
            201,
        )

        # Inject transparent rate and capacity headers
        response.headers["X-Quota-Limit"] = str(status_data["limit"])
        response.headers["X-Quota-Used"] = str(status_data["usage"])
        response.headers["X-Quota-Remaining"] = str(status_data["remaining"])
        response.headers["X-Quota-Alert"] = status_data["threshold_alert"] or "normal"
        return response
    finally:
        conn.close()


@usage_bp.route("/summary", methods=["GET"])
def get_usage_summary():
    """Retrieve current billing cycle aggregated usage and threshold alerts."""
    user_id = _resolve_user_id()
    db_path = current_app.config.get("DB_PATH", Config.DB_PATH)
    conn = get_db_connection(db_path)
    try:
        entitlements_service = EntitlementsService(conn)
        snapshot = entitlements_service.get_user_entitlements(user_id)
        return (
            jsonify(
                {
                    "user_id": user_id,
                    "plan_tier": snapshot["plan"]["tier"],
                    "usage_summary": snapshot["usage_summary"],
                }
            ),
            200,
        )
    finally:
        conn.close()
