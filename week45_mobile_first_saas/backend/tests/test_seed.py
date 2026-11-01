"""Unit tests for seed data, default plans, and demo accounts."""

import sqlite3

from app.models.schemas import Plan, Subscription
from data.seed import hash_password, seed_database, seed_demo_user


def test_seed_plans_created(db_conn: sqlite3.Connection):
    """Verify default plans are initialized with limits and features."""
    cursor = db_conn.cursor()
    cursor.execute("SELECT * FROM plans ORDER BY price_monthly_cents ASC;")
    rows = cursor.fetchall()
    plans = [Plan.from_row(row) for row in rows]
    cursor.close()

    assert len(plans) == 4
    tier_map = {p.tier: p for p in plans}

    assert "free" in tier_map
    assert tier_map["free"].price_monthly_cents == 0
    assert tier_map["free"].limits["max_projects"] == 1

    assert "starter" in tier_map
    assert tier_map["starter"].price_monthly_cents == 1900
    assert "export_data" in tier_map["starter"].features

    assert "pro" in tier_map
    assert tier_map["pro"].price_monthly_cents == 4900
    assert tier_map["pro"].limits["monthly_api_calls"] == 50000

    assert "enterprise" in tier_map
    assert tier_map["enterprise"].price_monthly_cents == 19900
    assert "sso" in tier_map["enterprise"].features


def test_seed_database_idempotency(db_conn: sqlite3.Connection):
    """Verify seed_database can be executed multiple times without constraint errors."""
    seed_database(db_conn)
    seed_database(db_conn)

    cursor = db_conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM plans;")
    count = cursor.fetchone()[0]
    cursor.close()
    assert count == 4


def test_demo_user_and_subscription(db_conn: sqlite3.Connection):
    """Verify demo user Alice and her active subscription exist in seeded database."""
    seed_demo_user(db_conn)
    cursor = db_conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = 'usr_demo_alice';")
    user_row = cursor.fetchone()
    assert user_row is not None
    assert user_row["email"] == "alice@pulsesub.io"

    cursor.execute("SELECT * FROM subscriptions WHERE user_id = 'usr_demo_alice';")
    sub_row = cursor.fetchone()
    assert sub_row is not None
    sub = Subscription.from_row(sub_row)
    assert sub.plan_id == "plan_pro"
    assert sub.status == "active"
    cursor.close()


def test_hash_password_deterministic():
    """Verify password hashing produces consistent SHA256 output with salt."""
    hash1 = hash_password("Secret123")
    hash2 = hash_password("Secret123")
    hash3 = hash_password("DifferentSecret")
    assert hash1 == hash2
    assert hash1 != hash3
    assert len(hash1) == 64
