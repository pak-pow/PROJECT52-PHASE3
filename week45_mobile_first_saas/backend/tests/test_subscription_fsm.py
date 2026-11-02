"""Unit tests for Subscription Lifecycle Finite State Machine (FSM)."""

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from app.billing.subscription_fsm import (
    InvalidStateTransitionError,
    SubscriptionExpiredError,
    SubscriptionFSM,
)
from app.models.schemas import BillingInterval, Subscription, SubscriptionStatus
from data.seed import seed_demo_user


@pytest.fixture
def base_sub() -> Subscription:
    """Provide a standard in-memory Subscription fixture."""
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=15)
    end = now + timedelta(days=15)
    fmt = "%Y-%m-%d %H:%M:%S"
    return Subscription(
        id="sub_fsm_test",
        user_id="usr_demo_alice",
        plan_id="plan_starter",
        billing_interval=BillingInterval.MONTHLY.value,
        status=SubscriptionStatus.ACTIVE.value,
        current_period_start=start.strftime(fmt),
        current_period_end=end.strftime(fmt),
        cancel_at_period_end=False,
        canceled_at=None,
    )


def test_fsm_initial_status(base_sub: Subscription):
    """Verify FSM status property reflects underlying subscription."""
    fsm = SubscriptionFSM(base_sub)
    assert fsm.status == SubscriptionStatus.ACTIVE.value


def test_fsm_mark_past_due(base_sub: Subscription):
    """Verify transitioning from ACTIVE to PAST_DUE on payment failure."""
    fsm = SubscriptionFSM(base_sub)
    sub = fsm.mark_past_due()
    assert sub.status == SubscriptionStatus.PAST_DUE.value
    assert fsm.status == SubscriptionStatus.PAST_DUE.value


def test_fsm_activate_from_past_due(base_sub: Subscription):
    """Verify resolving past due status on successful retry."""
    base_sub.status = SubscriptionStatus.PAST_DUE.value
    fsm = SubscriptionFSM(base_sub)
    sub = fsm.activate()
    assert sub.status == SubscriptionStatus.ACTIVE.value


def test_fsm_cancel_at_period_end(base_sub: Subscription):
    """Verify non-immediate cancel keeps status active but sets period-end flag."""
    fsm = SubscriptionFSM(base_sub)
    sub = fsm.cancel(immediate=False)
    assert sub.status == SubscriptionStatus.ACTIVE.value
    assert sub.cancel_at_period_end is True
    assert sub.canceled_at is not None


def test_fsm_cancel_immediate(base_sub: Subscription):
    """Verify immediate cancellation transitions to CANCELED status."""
    fsm = SubscriptionFSM(base_sub)
    sub = fsm.cancel(immediate=True)
    assert sub.status == SubscriptionStatus.CANCELED.value
    assert sub.cancel_at_period_end is False
    assert sub.canceled_at is not None


def test_fsm_resume_scheduled_cancel(base_sub: Subscription):
    """Verify resuming a subscription scheduled to cancel resets the flag."""
    base_sub.cancel_at_period_end = True
    base_sub.canceled_at = "2026-11-01 00:00:00"
    fsm = SubscriptionFSM(base_sub)
    sub = fsm.resume()
    assert sub.cancel_at_period_end is False
    assert sub.canceled_at is None
    assert sub.status == SubscriptionStatus.ACTIVE.value


def test_fsm_resume_immediate_canceled_before_expiry(base_sub: Subscription):
    """Verify resuming immediately canceled subscription restores active."""
    base_sub.status = SubscriptionStatus.CANCELED.value
    base_sub.canceled_at = "2026-11-01 00:00:00"
    fsm = SubscriptionFSM(base_sub)
    sub = fsm.resume()
    assert sub.status == SubscriptionStatus.ACTIVE.value
    assert sub.canceled_at is None


def test_fsm_resume_immediate_canceled_after_expiry_raises(base_sub: Subscription):
    """Verify resuming a canceled subscription after period end raises error."""
    base_sub.status = SubscriptionStatus.CANCELED.value
    base_sub.current_period_end = "2020-01-01 00:00:00"
    fsm = SubscriptionFSM(base_sub)
    with pytest.raises(SubscriptionExpiredError):
        fsm.resume()


def test_fsm_resume_active_non_canceled_raises(base_sub: Subscription):
    """Verify resuming an already active non-canceled subscription raises error."""
    base_sub.cancel_at_period_end = False
    fsm = SubscriptionFSM(base_sub)
    with pytest.raises(InvalidStateTransitionError):
        fsm.resume()


def test_fsm_expire_terminal_state(base_sub: Subscription):
    """Verify terminal EXPIRED state cannot be activated or renewed."""
    base_sub.status = SubscriptionStatus.PAST_DUE.value
    fsm = SubscriptionFSM(base_sub)
    sub = fsm.expire()
    assert sub.status == SubscriptionStatus.EXPIRED.value

    with pytest.raises(InvalidStateTransitionError):
        fsm.activate()

    now = datetime.now(timezone.utc)
    with pytest.raises(SubscriptionExpiredError):
        fsm.renew(now, now + timedelta(days=30))

    with pytest.raises(SubscriptionExpiredError):
        fsm.change_tier("plan_pro")


def test_fsm_renew_active(base_sub: Subscription):
    """Verify renewal advances period start and end while maintaining active status."""
    fsm = SubscriptionFSM(base_sub)
    now = datetime.now(timezone.utc)
    next_start = now
    next_end = now + timedelta(days=30)
    sub = fsm.renew(next_start, next_end)
    assert sub.status == SubscriptionStatus.ACTIVE.value
    assert sub.current_period_start == next_start.strftime("%Y-%m-%d %H:%M:%S")
    assert sub.current_period_end == next_end.strftime("%Y-%m-%d %H:%M:%S")


def test_fsm_change_tier(base_sub: Subscription):
    """Verify tier and interval changes update plan_id and interval."""
    fsm = SubscriptionFSM(base_sub)
    sub = fsm.change_tier("plan_enterprise", BillingInterval.ANNUAL)
    assert sub.plan_id == "plan_enterprise"
    assert sub.billing_interval == "annual"


def test_fsm_database_persistence(db_conn: sqlite3.Connection, base_sub: Subscription):
    """Verify FSM changes persist to database when connection is supplied."""
    seed_demo_user(db_conn)
    cursor = db_conn.cursor()
    cursor.execute(
        """
        INSERT INTO subscriptions (
            id, user_id, plan_id, billing_interval, status,
            current_period_start, current_period_end
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?
        );
        """,
        (
            base_sub.id,
            base_sub.user_id,
            base_sub.plan_id,
            base_sub.billing_interval,
            base_sub.status,
            base_sub.current_period_start,
            base_sub.current_period_end,
        ),
    )
    db_conn.commit()

    fsm = SubscriptionFSM(base_sub, conn=db_conn)
    fsm.mark_past_due()

    cursor.execute("SELECT status FROM subscriptions WHERE id = ?;", (base_sub.id,))
    row = cursor.fetchone()
    assert row["status"] == "past_due"
    cursor.close()
