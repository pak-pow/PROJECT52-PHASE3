"""Seed data for PulseSub plans, demo users, and initial subscriptions."""

import hashlib
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path


def hash_password(password: str) -> str:
    """Generate deterministic salted SHA256 password hash for local testing."""
    salt = "pulsesub_demo_salt_2026"
    return hashlib.sha256(f"{salt}_{password}".encode("utf-8")).hexdigest()


DEFAULT_PLANS = [
    {
        "id": "plan_free",
        "name": "Free",
        "tier": "free",
        "price_monthly_cents": 0,
        "price_annual_cents": 0,
        "limits": {
            "max_projects": 1,
            "monthly_api_calls": 100,
            "team_seats": 1,
            "storage_mb": 50,
        },
        "features": [
            "basic_analytics",
            "community_support",
        ],
        "is_active": 1,
    },
    {
        "id": "plan_starter",
        "name": "Starter",
        "tier": "starter",
        "price_monthly_cents": 1900,
        "price_annual_cents": 19000,
        "limits": {
            "max_projects": 5,
            "monthly_api_calls": 5000,
            "team_seats": 2,
            "storage_mb": 500,
        },
        "features": [
            "basic_analytics",
            "email_support",
            "export_data",
        ],
        "is_active": 1,
    },
    {
        "id": "plan_pro",
        "name": "Pro",
        "tier": "pro",
        "price_monthly_cents": 4900,
        "price_annual_cents": 49000,
        "limits": {
            "max_projects": -1,
            "monthly_api_calls": 50000,
            "team_seats": 5,
            "storage_mb": 5000,
        },
        "features": [
            "basic_analytics",
            "email_support",
            "export_data",
            "custom_domains",
            "team_collaboration",
            "priority_support",
        ],
        "is_active": 1,
    },
    {
        "id": "plan_enterprise",
        "name": "Enterprise",
        "tier": "enterprise",
        "price_monthly_cents": 19900,
        "price_annual_cents": 199000,
        "limits": {
            "max_projects": -1,
            "monthly_api_calls": 500000,
            "team_seats": -1,
            "storage_mb": 50000,
        },
        "features": [
            "basic_analytics",
            "email_support",
            "export_data",
            "custom_domains",
            "team_collaboration",
            "priority_support",
            "audit_logs",
            "sso",
            "dedicated_sla",
        ],
        "is_active": 1,
    },
]


def seed_plans(conn: sqlite3.Connection) -> None:
    """Insert or update the default pricing tier plans."""
    cursor = conn.cursor()
    for plan in DEFAULT_PLANS:
        cursor.execute(
            """
            INSERT OR REPLACE INTO plans (
                id, name, tier, price_monthly_cents, price_annual_cents,
                limits_json, features_json, is_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                plan["id"],
                plan["name"],
                plan["tier"],
                plan["price_monthly_cents"],
                plan["price_annual_cents"],
                json.dumps(plan["limits"]),
                json.dumps(plan["features"]),
                plan["is_active"],
            ),
        )
    conn.commit()


def seed_demo_user(conn: sqlite3.Connection) -> None:
    """Seed demo accounts, active subscription, invoice, and initial usage."""
    cursor = conn.cursor()
    now = datetime.now(timezone.utc)
    start_date = now - timedelta(days=12)
    end_date = start_date + timedelta(days=30)
    iso_now = now.strftime("%Y-%m-%d %H:%M:%S")
    iso_start = start_date.strftime("%Y-%m-%d %H:%M:%S")
    iso_end = end_date.strftime("%Y-%m-%d %H:%M:%S")

    # Demo User: Alice (Pro Tier Subscriber)
    cursor.execute(
        """
        INSERT OR REPLACE INTO users (
            id, email, password_hash, full_name, role, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?);
        """,
        (
            "usr_demo_alice",
            "alice@pulsesub.io",
            hash_password("PulseSubSecret2026"),
            "Alice Vance",
            "user",
            iso_start,
            iso_now,
        ),
    )

    # Demo Subscription for Alice
    cursor.execute(
        """
        INSERT OR REPLACE INTO subscriptions (
            id, user_id, plan_id, billing_interval, status,
            current_period_start, current_period_end, cancel_at_period_end,
            canceled_at, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """,
        (
            "sub_demo_alice_pro",
            "usr_demo_alice",
            "plan_pro",
            "monthly",
            "active",
            iso_start,
            iso_end,
            0,
            None,
            iso_start,
            iso_now,
        ),
    )

    # Demo Paid Invoice
    invoice_items = [
        {
            "description": "PulseSub Pro Plan (Monthly Recurring)",
            "unit_amount_cents": 4900,
            "quantity": 1,
            "proration": False,
        }
    ]
    cursor.execute(
        """
        INSERT OR REPLACE INTO invoices (
            id, user_id, subscription_id, invoice_number,
            amount_due_cents, amount_paid_cents, currency, status,
            line_items_json, payment_attempt_count, due_date, paid_at, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """,
        (
            "inv_demo_2026_0001",
            "usr_demo_alice",
            "sub_demo_alice_pro",
            "INV-2026-0001",
            4900,
            4900,
            "usd",
            "paid",
            json.dumps(invoice_items),
            1,
            iso_start,
            iso_start,
            iso_start,
        ),
    )

    # Demo Usage Records
    cursor.execute(
        """
        INSERT OR REPLACE INTO usage_records (
            id, user_id, subscription_id, metric_key, quantity,
            idempotency_key, recorded_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?);
        """,
        (
            "use_demo_api_001",
            "usr_demo_alice",
            "sub_demo_alice_pro",
            "monthly_api_calls",
            1420,
            "idem_demo_seed_api_001",
            iso_now,
        ),
    )

    conn.commit()


def seed_database(conn: sqlite3.Connection) -> None:
    """Execute complete database seeding for plans and demo data."""
    seed_plans(conn)
    seed_demo_user(conn)


if __name__ == "__main__":
    db_file = Path(__file__).resolve().parent / "pulsesub.db"
    schema_file = Path(__file__).resolve().parent / "schema.sql"

    print(f"Connecting to database at {db_file}...")
    c = sqlite3.connect(str(db_file))
    c.executescript(schema_file.read_text(encoding="utf-8"))
    seed_database(c)
    c.close()
    print("Database seeding completed successfully.")
