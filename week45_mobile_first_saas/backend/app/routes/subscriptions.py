"""Customer subscription management, tier changes, and proration routes."""

import uuid
from datetime import datetime, timedelta, timezone

from flask import Blueprint, current_app, jsonify, request

from app.billing.invoice_service import InvoiceService
from app.billing.proration import calculate_proration
from app.billing.subscription_fsm import (
    InvalidStateTransitionError,
    SubscriptionExpiredError,
    SubscriptionFSM,
)
from app.config.settings import Config
from app.db.connection import get_db_connection
from app.models.schemas import BillingInterval, Plan, Subscription, SubscriptionStatus
from app.services.decorators import _resolve_user_id
from app.services.entitlements_service import EntitlementsService

subscriptions_bp = Blueprint(
    "subscriptions", __name__, url_prefix="/api/v1/subscriptions"
)


@subscriptions_bp.route("/current", methods=["GET"])
def get_current_subscription():
    """Retrieve active subscription, tier specifications, and remaining cycle days."""
    user_id = _resolve_user_id()
    db_path = current_app.config.get("DB_PATH", Config.DB_PATH)
    conn = get_db_connection(db_path)
    try:
        entitlements_service = EntitlementsService(conn)
        plan, subscription = entitlements_service.get_user_plan(user_id)

        days_remaining = 0
        if subscription:
            try:
                now = datetime.now(timezone.utc)
                if isinstance(subscription.current_period_end, datetime):
                    end_dt = subscription.current_period_end
                else:
                    end_dt = datetime.strptime(
                        str(subscription.current_period_end), "%Y-%m-%d %H:%M:%S"
                    )
                if end_dt.tzinfo is None:
                    end_dt = end_dt.replace(tzinfo=timezone.utc)
                diff = (end_dt - now).total_seconds()
                days_remaining = max(0, int(diff // 86400))
            except (ValueError, TypeError):
                days_remaining = 0

        return (
            jsonify(
                {
                    "user_id": user_id,
                    "plan": plan.to_dict(),
                    "subscription": subscription.to_dict() if subscription else None,
                    "days_remaining": days_remaining,
                    "is_active": (
                        subscription is not None
                        and subscription.status
                        in (
                            SubscriptionStatus.ACTIVE.value,
                            SubscriptionStatus.TRIALING.value,
                        )
                    ),
                }
            ),
            200,
        )
    finally:
        conn.close()


@subscriptions_bp.route("/subscribe", methods=["POST"])
def subscribe():
    """Create a new subscription for the user and issue an initial invoice."""
    user_id = _resolve_user_id()
    payload = request.get_json(silent=True) or {}
    plan_id = payload.get("plan_id")
    billing_interval_raw = payload.get("billing_interval", "monthly").lower()

    if not plan_id:
        return (
            jsonify(
                {
                    "error": "invalid_payload",
                    "message": "Field 'plan_id' is required.",
                }
            ),
            400,
        )

    if billing_interval_raw not in ("monthly", "annual"):
        return (
            jsonify(
                {
                    "error": "invalid_interval",
                    "message": "Billing interval must be 'monthly' or 'annual'.",
                }
            ),
            400,
        )

    db_path = current_app.config.get("DB_PATH", Config.DB_PATH)
    conn = get_db_connection(db_path)
    try:
        entitlements_service = EntitlementsService(conn)
        existing_sub = entitlements_service.get_active_subscription(user_id)
        if existing_sub and existing_sub.status == SubscriptionStatus.ACTIVE.value:
            return (
                jsonify(
                    {
                        "error": "already_subscribed",
                        "message": (
                            "User already has an active subscription. "
                            "Use /change-tier to upgrade or switch plans."
                        ),
                        "subscription_id": existing_sub.id,
                    }
                ),
                409,
            )

        cursor = conn.cursor()
        cursor.execute("SELECT * FROM plans WHERE id = ?;", (plan_id,))
        plan_row = cursor.fetchone()
        cursor.close()

        if not plan_row:
            return (
                jsonify(
                    {
                        "error": "plan_not_found",
                        "message": f"Plan with ID '{plan_id}' does not exist.",
                    }
                ),
                404,
            )

        plan = Plan.from_row(plan_row)
        now = datetime.now(timezone.utc)
        fmt = "%Y-%m-%d %H:%M:%S"
        iso_now = now.strftime(fmt)

        duration_days = 365 if billing_interval_raw == "annual" else 30
        end_date = now + timedelta(days=duration_days)
        iso_end = end_date.strftime(fmt)

        sub_id = f"sub_{uuid.uuid4().hex[:12]}"
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO subscriptions (
                id, user_id, plan_id, billing_interval, status,
                current_period_start, current_period_end,
                cancel_at_period_end, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?);
            """,
            (
                sub_id,
                user_id,
                plan.id,
                billing_interval_raw,
                SubscriptionStatus.ACTIVE.value,
                iso_now,
                iso_end,
                iso_now,
                iso_now,
            ),
        )
        conn.commit()
        cursor.close()

        # Generate initial invoice
        amount = (
            plan.price_annual_cents
            if billing_interval_raw == "annual"
            else plan.price_monthly_cents
        )
        interval_title = billing_interval_raw.capitalize()
        line_items = [
            {
                "description": f"{plan.name} Plan ({interval_title})",
                "unit_amount_cents": amount,
                "quantity": 1,
            }
        ]
        invoice_service = InvoiceService(conn)
        invoice = invoice_service.create_invoice(
            user_id=user_id,
            subscription_id=sub_id,
            line_items=line_items,
            due_days=0,
            auto_pay=True,
        )

        cursor = conn.cursor()
        cursor.execute("SELECT * FROM subscriptions WHERE id = ?;", (sub_id,))
        created_sub_row = cursor.fetchone()
        cursor.close()
        sub_obj = Subscription.from_row(created_sub_row)

        return (
            jsonify(
                {
                    "subscription": sub_obj.to_dict(),
                    "invoice": invoice.to_dict(),
                    "message": "Subscription created successfully.",
                }
            ),
            201,
        )
    finally:
        conn.close()


@subscriptions_bp.route("/change-tier", methods=["POST"])
def change_tier():
    """Adjust plan tier or interval and calculate proration."""
    user_id = _resolve_user_id()
    payload = request.get_json(silent=True) or {}
    new_plan_id = payload.get("new_plan_id")
    new_interval_raw = payload.get("new_interval")
    preview_only = bool(payload.get("preview_only", False))

    if not new_plan_id:
        return (
            jsonify(
                {
                    "error": "invalid_payload",
                    "message": "Field 'new_plan_id' is required.",
                }
            ),
            400,
        )

    db_path = current_app.config.get("DB_PATH", Config.DB_PATH)
    conn = get_db_connection(db_path)
    try:
        entitlements_service = EntitlementsService(conn)
        current_sub = entitlements_service.get_active_subscription(user_id)
        if not current_sub:
            return (
                jsonify(
                    {
                        "error": "no_active_subscription",
                        "message": (
                            "No active subscription found. "
                            "Use /subscribe to create a subscription first."
                        ),
                    }
                ),
                404,
            )

        cursor = conn.cursor()
        cursor.execute("SELECT * FROM plans WHERE id = ?;", (current_sub.plan_id,))
        curr_plan_row = cursor.fetchone()
        cursor.execute("SELECT * FROM plans WHERE id = ?;", (new_plan_id,))
        new_plan_row = cursor.fetchone()
        cursor.close()

        if not new_plan_row:
            return (
                jsonify(
                    {
                        "error": "plan_not_found",
                        "message": f"Target plan '{new_plan_id}' does not exist.",
                    }
                ),
                404,
            )

        current_plan = Plan.from_row(curr_plan_row)
        new_plan = Plan.from_row(new_plan_row)

        target_interval = (
            BillingInterval(new_interval_raw.lower()) if new_interval_raw else None
        )

        # Check if plan and interval are identical
        interval_unchanged = (
            target_interval is None
            or target_interval.value == current_sub.billing_interval
        )
        if current_sub.plan_id == new_plan.id and interval_unchanged:
            return (
                jsonify(
                    {
                        "error": "same_plan",
                        "message": (
                            "Target plan and interval are identical "
                            "to current subscription."
                        ),
                    }
                ),
                400,
            )

        # Calculate exact linear proration
        proration = calculate_proration(
            current_plan=current_plan,
            new_plan=new_plan,
            subscription=current_sub,
            target_interval=target_interval,
        )

        if preview_only:
            return (
                jsonify(
                    {
                        "preview_only": True,
                        "proration": proration.to_dict(),
                    }
                ),
                200,
            )

        # Execute subscription update and invoice issuance
        invoice_service = InvoiceService(conn)
        invoice = invoice_service.create_proration_invoice(
            user_id=user_id,
            subscription_id=current_sub.id,
            proration_result=proration,
            auto_pay=True,
        )

        fsm = SubscriptionFSM(current_sub, conn)
        updated_sub = fsm.change_tier(
            new_plan_id=new_plan.id,
            new_interval=target_interval,
        )

        return (
            jsonify(
                {
                    "subscription": updated_sub.to_dict(),
                    "proration": proration.to_dict(),
                    "invoice": invoice.to_dict(),
                    "message": "Subscription tier updated successfully.",
                }
            ),
            200,
        )
    finally:
        conn.close()


@subscriptions_bp.route("/cancel", methods=["POST"])
def cancel_subscription():
    """Cancel subscription immediately or schedule cancellation for period end."""
    user_id = _resolve_user_id()
    payload = request.get_json(silent=True) or {}
    immediate = bool(payload.get("immediate", False))

    db_path = current_app.config.get("DB_PATH", Config.DB_PATH)
    conn = get_db_connection(db_path)
    try:
        entitlements_service = EntitlementsService(conn)
        current_sub = entitlements_service.get_active_subscription(user_id)
        if not current_sub:
            return (
                jsonify(
                    {
                        "error": "no_active_subscription",
                        "message": "No active subscription to cancel.",
                    }
                ),
                404,
            )

        fsm = SubscriptionFSM(current_sub, conn)
        try:
            updated_sub = fsm.cancel(immediate=immediate)
        except InvalidStateTransitionError as exc:
            return (
                jsonify({"error": "invalid_transition", "message": str(exc)}),
                400,
            )

        message = (
            "Subscription canceled immediately."
            if immediate
            else "Subscription scheduled for cancellation at period end."
        )
        return (
            jsonify(
                {
                    "subscription": updated_sub.to_dict(),
                    "message": message,
                }
            ),
            200,
        )
    finally:
        conn.close()


@subscriptions_bp.route("/resume", methods=["POST"])
def resume_subscription():
    """Reactivate a subscription that was scheduled to cancel or canceled."""
    user_id = _resolve_user_id()
    db_path = current_app.config.get("DB_PATH", Config.DB_PATH)
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM subscriptions
            WHERE user_id = ?
            ORDER BY current_period_end DESC
            LIMIT 1;
            """,
            (user_id,),
        )
        row = cursor.fetchone()
        cursor.close()

        if not row:
            return (
                jsonify(
                    {
                        "error": "no_subscription_found",
                        "message": "No subscription found to resume.",
                    }
                ),
                404,
            )

        sub = Subscription.from_row(row)
        fsm = SubscriptionFSM(sub, conn)
        try:
            updated_sub = fsm.resume()
        except (InvalidStateTransitionError, SubscriptionExpiredError) as exc:
            return (
                jsonify({"error": "resume_failed", "message": str(exc)}),
                400,
            )

        return (
            jsonify(
                {
                    "subscription": updated_sub.to_dict(),
                    "message": "Subscription resumed successfully.",
                }
            ),
            200,
        )
    finally:
        conn.close()
