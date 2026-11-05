"""Feature gatekeeping, subscription resolution, and entitlements engine."""

import sqlite3
from typing import Any, Dict, Optional, Tuple

from app.models.schemas import Plan, Subscription, SubscriptionStatus
from app.services.usage_service import UsageService


class EntitlementsService:
    """Service resolving plan capabilities, feature flags, and quotas."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        usage_service: Optional[UsageService] = None,
    ):
        self.conn = conn
        self.usage_service = usage_service or UsageService(conn)

    def get_active_subscription(self, user_id: str) -> Optional[Subscription]:
        """Fetch the current active or grace-period subscription for a user."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT * FROM subscriptions
            WHERE user_id = ?
              AND status IN (?, ?, ?)
            ORDER BY current_period_end DESC
            LIMIT 1;
            """,
            (
                user_id,
                SubscriptionStatus.ACTIVE.value,
                SubscriptionStatus.TRIALING.value,
                SubscriptionStatus.PAST_DUE.value,
            ),
        )
        row = cursor.fetchone()
        cursor.close()

        if not row:
            return None
        return Subscription.from_row(row)

    def get_fallback_free_plan(self) -> Plan:
        """Retrieve the default Free tier plan from the database."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM plans WHERE tier = 'free' LIMIT 1;")
        row = cursor.fetchone()
        cursor.close()
        if not row:
            raise RuntimeError("Default free plan not found in database.")
        return Plan.from_row(row)

    def get_user_plan(self, user_id: str) -> Tuple[Plan, Optional[Subscription]]:
        """Resolve effective plan and active subscription for user."""
        subscription = self.get_active_subscription(user_id)
        if subscription:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT * FROM plans WHERE id = ?;",
                (subscription.plan_id,),
            )
            row = cursor.fetchone()
            cursor.close()
            if row:
                return Plan.from_row(row), subscription

        # Fallback to Free plan if no active subscription
        return self.get_fallback_free_plan(), None

    def check_feature_access(self, user_id: str, feature_key: str) -> bool:
        """Determine if a user is entitled to a specific boolean feature flag."""
        plan, _ = self.get_user_plan(user_id)
        return feature_key in plan.features

    def can_consume_metric(
        self,
        user_id: str,
        metric_key: str,
        requested_units: int = 1,
    ) -> Tuple[bool, Dict[str, Any]]:
        """Verify whether user has sufficient remaining quota for a metric."""
        plan, subscription = self.get_user_plan(user_id)
        limit = plan.limits.get(metric_key, 0)

        current_usage = self.usage_service.get_user_metric_usage(
            user_id=user_id,
            metric_key=metric_key,
            subscription=subscription,
        )

        status_data = self.usage_service.evaluate_quota_status(
            current_usage=current_usage,
            limit=limit,
        )

        if limit == -1:
            return True, status_data

        can_consume = (current_usage + requested_units) <= limit
        return can_consume, status_data

    def get_user_entitlements(self, user_id: str) -> Dict[str, Any]:
        """Compile complete entitlements and usage diagnostics snapshot for client."""
        plan, subscription = self.get_user_plan(user_id)

        usage_summary: Dict[str, Any] = {}
        for metric_key, limit in plan.limits.items():
            used = self.usage_service.get_user_metric_usage(
                user_id=user_id,
                metric_key=metric_key,
                subscription=subscription,
            )
            usage_summary[metric_key] = self.usage_service.evaluate_quota_status(
                current_usage=used,
                limit=limit,
            )

        return {
            "user_id": user_id,
            "plan": plan.to_dict(),
            "subscription": subscription.to_dict() if subscription else None,
            "features": plan.features,
            "limits": plan.limits,
            "usage_summary": usage_summary,
        }
