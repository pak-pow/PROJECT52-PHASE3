"""Customer feature entitlements and quota resolution routes."""

from flask import Blueprint, current_app, jsonify, request

from app.config.settings import Config
from app.db.connection import get_db_connection
from app.services.decorators import _resolve_user_id
from app.services.entitlements_service import EntitlementsService

entitlements_bp = Blueprint("entitlements", __name__, url_prefix="/api/v1/entitlements")


@entitlements_bp.route("/my-features", methods=["GET"])
def get_my_features():
    """Retrieve full entitlements, feature flags, limits, and usage diagnostics."""
    user_id = _resolve_user_id()
    db_path = current_app.config.get("DB_PATH", Config.DB_PATH)
    conn = get_db_connection(db_path)
    try:
        entitlements_service = EntitlementsService(conn)
        snapshot = entitlements_service.get_user_entitlements(user_id)
        return jsonify(snapshot), 200
    finally:
        conn.close()


@entitlements_bp.route("/check", methods=["GET"])
def check_feature():
    """Verify boolean entitlement access for a single feature flag."""
    feature_key = request.args.get("feature", "").strip()
    if not feature_key:
        return (
            jsonify(
                {
                    "error": "missing_parameter",
                    "message": "Query parameter 'feature' is required.",
                }
            ),
            400,
        )

    user_id = _resolve_user_id()
    db_path = current_app.config.get("DB_PATH", Config.DB_PATH)
    conn = get_db_connection(db_path)
    try:
        entitlements_service = EntitlementsService(conn)
        plan, _ = entitlements_service.get_user_plan(user_id)
        has_access = entitlements_service.check_feature_access(
            user_id=user_id,
            feature_key=feature_key,
        )

        return (
            jsonify(
                {
                    "user_id": user_id,
                    "feature": feature_key,
                    "allowed": has_access,
                    "plan_tier": plan.tier,
                }
            ),
            200,
        )
    finally:
        conn.close()
