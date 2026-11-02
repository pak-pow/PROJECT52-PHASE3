"""Subscription Lifecycle Finite State Machine (FSM) for PulseSub."""

import sqlite3
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

from app.models.schemas import BillingInterval, Subscription, SubscriptionStatus


class InvalidStateTransitionError(Exception):
    """Raised when an illegal lifecycle transition is attempted."""

    def __init__(self, current_status: str, target_status: str, reason: str = ""):
        message = f"Invalid transition from '{current_status}' to '{target_status}'"
        if reason:
            message += f": {reason}"
        super().__init__(message)
        self.current_status = current_status
        self.target_status = target_status
        self.reason = reason


class SubscriptionExpiredError(Exception):
    """Raised when an operation is attempted on an expired subscription."""

    pass


class SubscriptionFSM:
    """Finite State Machine controlling subscription lifecycle transitions.

    Supported States:
        - TRIALING: Active trial period with full or partial access.
        - ACTIVE: Fully paid and authorized recurring subscription.
        - PAST_DUE: Payment failed, entering grace period for dunning.
        - CANCELED: Subscription canceled, access may persist until period end.
        - EXPIRED: Terminal state where grace or cancelation period has ended.
    """

    ALLOWED_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
        SubscriptionStatus.TRIALING.value: (
            SubscriptionStatus.ACTIVE.value,
            SubscriptionStatus.CANCELED.value,
            SubscriptionStatus.EXPIRED.value,
        ),
        SubscriptionStatus.ACTIVE.value: (
            SubscriptionStatus.PAST_DUE.value,
            SubscriptionStatus.CANCELED.value,
            SubscriptionStatus.ACTIVE.value,  # Renew / tier change
        ),
        SubscriptionStatus.PAST_DUE.value: (
            SubscriptionStatus.ACTIVE.value,  # Successful retry
            SubscriptionStatus.CANCELED.value,
            SubscriptionStatus.EXPIRED.value,  # Grace period exceeded
        ),
        SubscriptionStatus.CANCELED.value: (
            SubscriptionStatus.ACTIVE.value,  # Resumed within period
            SubscriptionStatus.EXPIRED.value,  # Period ended
        ),
        SubscriptionStatus.EXPIRED.value: (),  # Terminal state
    }

    def __init__(
        self,
        subscription: Subscription,
        conn: Optional[sqlite3.Connection] = None,
    ):
        self.subscription = subscription
        self.conn = conn

    @property
    def status(self) -> str:
        """Return current status of subscription."""
        return self.subscription.status

    def _validate_transition(self, target_status: str) -> None:
        current = self.subscription.status
        allowed = self.ALLOWED_TRANSITIONS.get(current, ())
        if target_status not in allowed:
            raise InvalidStateTransitionError(
                current_status=current,
                target_status=target_status,
                reason=f"Permitted transitions from '{current}' are: {list(allowed)}",
            )

    def _persist(self) -> None:
        """Persist subscription updates to SQLite if connection is provided."""
        if self.conn is None:
            return

        cursor = self.conn.cursor()
        cursor.execute(
            """
            UPDATE subscriptions
            SET plan_id = ?,
                billing_interval = ?,
                status = ?,
                current_period_start = ?,
                current_period_end = ?,
                cancel_at_period_end = ?,
                canceled_at = ?,
                updated_at = ?
            WHERE id = ?;
            """,
            (
                self.subscription.plan_id,
                self.subscription.billing_interval,
                self.subscription.status,
                self.subscription.current_period_start,
                self.subscription.current_period_end,
                1 if self.subscription.cancel_at_period_end else 0,
                self.subscription.canceled_at,
                self.subscription.updated_at,
                self.subscription.id,
            ),
        )
        self.conn.commit()
        cursor.close()

    def activate(self, effective_at: Optional[datetime] = None) -> Subscription:
        """Transition subscription into ACTIVE state."""
        self._validate_transition(SubscriptionStatus.ACTIVE.value)

        now = effective_at or datetime.now(timezone.utc)
        self.subscription.status = SubscriptionStatus.ACTIVE.value
        self.subscription.cancel_at_period_end = False
        self.subscription.canceled_at = None
        self.subscription.updated_at = now.strftime("%Y-%m-%d %H:%M:%S")

        self._persist()
        return self.subscription

    def mark_past_due(self, failed_at: Optional[datetime] = None) -> Subscription:
        """Flag subscription as PAST_DUE when payment fails."""
        self._validate_transition(SubscriptionStatus.PAST_DUE.value)

        now = failed_at or datetime.now(timezone.utc)
        self.subscription.status = SubscriptionStatus.PAST_DUE.value
        self.subscription.updated_at = now.strftime("%Y-%m-%d %H:%M:%S")

        self._persist()
        return self.subscription

    def cancel(
        self, immediate: bool = False, canceled_at: Optional[datetime] = None
    ) -> Subscription:
        """Cancel subscription immediately or schedule for period end."""
        now = canceled_at or datetime.now(timezone.utc)
        iso_now = now.strftime("%Y-%m-%d %H:%M:%S")

        if immediate:
            self._validate_transition(SubscriptionStatus.CANCELED.value)
            self.subscription.status = SubscriptionStatus.CANCELED.value
            self.subscription.cancel_at_period_end = False
            self.subscription.canceled_at = iso_now
        else:
            # Scheduled cancellation at period end - state remains ACTIVE
            self.subscription.cancel_at_period_end = True
            self.subscription.canceled_at = iso_now

        self.subscription.updated_at = iso_now
        self._persist()
        return self.subscription

    def resume(self) -> Subscription:
        """Reactivate a subscription that was scheduled to cancel or canceled."""
        now = datetime.now(timezone.utc)
        iso_now = now.strftime("%Y-%m-%d %H:%M:%S")

        # Case 1: Active but scheduled to cancel at period end
        if (
            self.subscription.status == SubscriptionStatus.ACTIVE.value
            and self.subscription.cancel_at_period_end
        ):
            self.subscription.cancel_at_period_end = False
            self.subscription.canceled_at = None
            self.subscription.updated_at = iso_now
            self._persist()
            return self.subscription

        # Case 2: In CANCELED state, check if current_period_end has not expired
        if self.subscription.status == SubscriptionStatus.CANCELED.value:
            try:
                period_end = datetime.strptime(
                    self.subscription.current_period_end, "%Y-%m-%d %H:%M:%S"
                ).replace(tzinfo=timezone.utc)
                if now > period_end:
                    raise SubscriptionExpiredError(
                        "Cannot resume canceled subscription after period end."
                    )
            except ValueError:
                pass

            self._validate_transition(SubscriptionStatus.ACTIVE.value)
            self.subscription.status = SubscriptionStatus.ACTIVE.value
            self.subscription.cancel_at_period_end = False
            self.subscription.canceled_at = None
            self.subscription.updated_at = iso_now
            self._persist()
            return self.subscription

        raise InvalidStateTransitionError(
            current_status=self.subscription.status,
            target_status=SubscriptionStatus.ACTIVE.value,
            reason="Subscription is not in a resumable cancellation state.",
        )

    def expire(self, expired_at: Optional[datetime] = None) -> Subscription:
        """Transition into terminal EXPIRED state."""
        self._validate_transition(SubscriptionStatus.EXPIRED.value)

        now = expired_at or datetime.now(timezone.utc)
        self.subscription.status = SubscriptionStatus.EXPIRED.value
        self.subscription.updated_at = now.strftime("%Y-%m-%d %H:%M:%S")

        self._persist()
        return self.subscription

    def renew(
        self,
        new_period_start: datetime,
        new_period_end: datetime,
    ) -> Subscription:
        """Advance billing period upon successful payment cycle."""
        if self.subscription.status == SubscriptionStatus.EXPIRED.value:
            raise SubscriptionExpiredError("Cannot renew an expired subscription.")

        now = datetime.now(timezone.utc)
        self.subscription.status = SubscriptionStatus.ACTIVE.value
        self.subscription.current_period_start = new_period_start.strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        self.subscription.current_period_end = new_period_end.strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        self.subscription.cancel_at_period_end = False
        self.subscription.canceled_at = None
        self.subscription.updated_at = now.strftime("%Y-%m-%d %H:%M:%S")

        self._persist()
        return self.subscription

    def change_tier(
        self,
        new_plan_id: str,
        new_interval: Optional[BillingInterval] = None,
    ) -> Subscription:
        """Update subscription plan and billing interval."""
        if self.subscription.status == SubscriptionStatus.EXPIRED.value:
            raise SubscriptionExpiredError(
                "Cannot change plan on an expired subscription."
            )

        now = datetime.now(timezone.utc)
        self.subscription.plan_id = new_plan_id
        if new_interval is not None:
            self.subscription.billing_interval = new_interval.value
        self.subscription.updated_at = now.strftime("%Y-%m-%d %H:%M:%S")

        self._persist()
        return self.subscription
