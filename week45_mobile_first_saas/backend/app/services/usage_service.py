"""Metered resource consumption and quota threshold engine for PulseSub."""

import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.models.schemas import Subscription, UsageRecord


class UsageService:
    """Service for recording usage metrics, deduplicating, and tracking quotas."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def record_usage(
        self,
        user_id: str,
        metric_key: str,
        quantity: int = 1,
        subscription_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        recorded_at: Optional[datetime] = None,
    ) -> UsageRecord:
        """Record consumption of a quantitative metric with optional idempotency."""
        if quantity <= 0:
            raise ValueError(f"Quantity must be strictly positive, got {quantity}.")

        now = recorded_at or datetime.now(timezone.utc)
        iso_now = now.strftime("%Y-%m-%d %H:%M:%S")

        cursor = self.conn.cursor()

        # Idempotency check: if key already exists, return existing record
        if idempotency_key is not None:
            cursor.execute(
                """
                SELECT * FROM usage_records
                WHERE idempotency_key = ?;
                """,
                (idempotency_key,),
            )
            existing_row = cursor.fetchone()
            if existing_row:
                cursor.close()
                return UsageRecord.from_row(existing_row)

        record_id = f"use_{uuid.uuid4().hex[:12]}"
        cursor.execute(
            """
            INSERT INTO usage_records (
                id, user_id, subscription_id, metric_key,
                quantity, idempotency_key, recorded_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            (
                record_id,
                user_id,
                subscription_id,
                metric_key,
                quantity,
                idempotency_key,
                iso_now,
            ),
        )
        self.conn.commit()
        cursor.close()

        return UsageRecord(
            id=record_id,
            user_id=user_id,
            subscription_id=subscription_id,
            metric_key=metric_key,
            quantity=quantity,
            idempotency_key=idempotency_key,
            recorded_at=iso_now,
        )

    def get_period_usage(
        self,
        user_id: str,
        metric_key: str,
        period_start: str,
        period_end: str,
    ) -> int:
        """Sum total usage quantity for a metric within an interval."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT COALESCE(SUM(quantity), 0) AS total_used
            FROM usage_records
            WHERE user_id = ?
              AND metric_key = ?
              AND recorded_at >= ?
              AND recorded_at <= ?;
            """,
            (user_id, metric_key, period_start, period_end),
        )
        row = cursor.fetchone()
        cursor.close()
        return int(row["total_used"]) if row else 0

    def get_user_metric_usage(
        self,
        user_id: str,
        metric_key: str,
        subscription: Optional[Subscription] = None,
    ) -> int:
        """Resolve current usage based on subscription billing cycle."""
        has_window = (
            subscription
            and subscription.current_period_start
            and subscription.current_period_end
        )
        if has_window:
            return self.get_period_usage(
                user_id=user_id,
                metric_key=metric_key,
                period_start=subscription.current_period_start,
                period_end=subscription.current_period_end,
            )

        # Fallback for users without subscription (all-time usage for metric)
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT COALESCE(SUM(quantity), 0) AS total_used
            FROM usage_records
            WHERE user_id = ? AND metric_key = ?;
            """,
            (user_id, metric_key),
        )
        row = cursor.fetchone()
        cursor.close()
        return int(row["total_used"]) if row else 0

    @staticmethod
    def evaluate_quota_status(
        current_usage: int,
        limit: int,
    ) -> Dict[str, Any]:
        """Compute quota percentage, capacity alerts, and status."""
        if limit == -1:
            return {
                "usage": current_usage,
                "limit": -1,
                "remaining": -1,
                "percentage": 0.0,
                "is_over_quota": False,
                "threshold_alert": None,
                "unlimited": True,
            }

        remaining = max(0, limit - current_usage)
        percentage = round((current_usage / limit) * 100, 1) if limit > 0 else 100.0
        is_over_quota = current_usage >= limit

        threshold_alert: Optional[str] = None
        if current_usage >= limit:
            threshold_alert = "100%"
        elif limit > 0 and current_usage >= (limit * 0.9):
            threshold_alert = "90%"
        elif limit > 0 and current_usage >= (limit * 0.8):
            threshold_alert = "80%"

        return {
            "usage": current_usage,
            "limit": limit,
            "remaining": remaining,
            "percentage": min(100.0, percentage),
            "is_over_quota": is_over_quota,
            "threshold_alert": threshold_alert,
            "unlimited": False,
        }
