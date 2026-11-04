"""Public pricing tiers and plan specification routes."""

from flask import Blueprint, current_app, jsonify

from app.config.settings import Config
from app.db.connection import get_db_connection
from app.models.schemas import Plan

plans_bp = Blueprint("plans", __name__, url_prefix="/api/v1/plans")


@plans_bp.route("", methods=["GET"])
@plans_bp.route("/", methods=["GET"])
def list_plans():
    """List all publicly available active subscription plans."""
    db_path = current_app.config.get("DB_PATH", Config.DB_PATH)
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM plans
            WHERE is_active = 1
            ORDER BY price_monthly_cents ASC;
            """)
        rows = cursor.fetchall()
        cursor.close()

        plans = [Plan.from_row(row).to_dict() for row in rows]
        return jsonify({"plans": plans, "total": len(plans)}), 200
    finally:
        conn.close()


@plans_bp.route("/<plan_id>", methods=["GET"])
def get_plan(plan_id: str):
    """Retrieve details, quotas, and feature flags for a specific plan."""
    db_path = current_app.config.get("DB_PATH", Config.DB_PATH)
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM plans WHERE id = ?;", (plan_id,))
        row = cursor.fetchone()
        cursor.close()

        if not row:
            return (
                jsonify(
                    {
                        "error": "plan_not_found",
                        "message": f"Plan with ID '{plan_id}' does not exist.",
                    }
                ),
                404,
            )

        plan = Plan.from_row(row)
        return jsonify({"plan": plan.to_dict()}), 200
    finally:
        conn.close()
