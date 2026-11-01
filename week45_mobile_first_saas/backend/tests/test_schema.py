"""Unit tests for SQLite schema tables, constraints, foreign keys, and indexes."""

import sqlite3

import pytest


def test_schema_tables_exist(db_conn: sqlite3.Connection):
    """Verify that all core SaaS tables are created successfully."""
    cursor = db_conn.cursor()
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name NOT LIKE 'sqlite_%';
        """)
    tables = {row["name"] for row in cursor.fetchall()}
    cursor.close()

    expected_tables = {
        "users",
        "plans",
        "subscriptions",
        "invoices",
        "usage_records",
        "webhook_events",
    }
    assert expected_tables.issubset(tables)


def test_schema_indexes_exist(db_conn: sqlite3.Connection):
    """Verify that all required performance indexes exist."""
    cursor = db_conn.cursor()
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='index' AND name NOT LIKE 'sqlite_%';
        """)
    indexes = {row["name"] for row in cursor.fetchall()}
    cursor.close()

    expected_indexes = {
        "idx_users_email",
        "idx_subscriptions_user",
        "idx_subscriptions_status",
        "idx_invoices_user",
        "idx_invoices_sub",
        "idx_invoices_status",
        "idx_usage_user_metric",
        "idx_webhook_events_id",
        "idx_webhook_events_status",
    }
    assert expected_indexes.issubset(indexes)


def test_users_unique_email_constraint(db_conn: sqlite3.Connection):
    """Verify unique constraint on users(email)."""
    cursor = db_conn.cursor()
    cursor.execute("""
        INSERT INTO users (id, email, password_hash, full_name)
        VALUES ('u1', 'test@pulse.io', 'hash123', 'Tester');
        """)
    db_conn.commit()

    with pytest.raises(sqlite3.IntegrityError):
        cursor.execute("""
            INSERT INTO users (id, email, password_hash, full_name)
            VALUES ('u2', 'test@pulse.io', 'hash456', 'Duplicate Tester');
            """)
    cursor.close()


def test_plans_tier_and_price_check_constraints(db_conn: sqlite3.Connection):
    """Verify check constraints for plan tiers and non-negative pricing."""
    cursor = db_conn.cursor()

    # Invalid tier
    with pytest.raises(sqlite3.IntegrityError):
        cursor.execute("""
            INSERT INTO plans (id, name, tier, price_monthly_cents, price_annual_cents)
            VALUES ('p_bad', 'Bad Plan', 'super_vip', 1000, 10000);
            """)

    # Negative price
    with pytest.raises(sqlite3.IntegrityError):
        cursor.execute("""
            INSERT INTO plans (id, name, tier, price_monthly_cents, price_annual_cents)
            VALUES ('p_neg', 'Neg Plan', 'free', -50, 0);
            """)
    cursor.close()


def test_foreign_key_cascade_deletion(db_conn: sqlite3.Connection):
    """Verify deleting a user cascades and removes their subscriptions and invoices."""
    cursor = db_conn.cursor()

    # Insert user
    cursor.execute("""
        INSERT INTO users (id, email, password_hash, full_name)
        VALUES ('usr_cascade', 'cascade@pulse.io', 'hash', 'Cascade User');
        """)

    # Insert subscription
    cursor.execute("""
        INSERT INTO subscriptions (
            id, user_id, plan_id, billing_interval, status,
            current_period_start, current_period_end
        ) VALUES (
            'sub_cascade', 'usr_cascade', 'plan_pro', 'monthly', 'active',
            '2026-11-01 00:00:00', '2026-12-01 00:00:00'
        );
        """)

    # Insert invoice
    cursor.execute("""
        INSERT INTO invoices (
            id, user_id, subscription_id, invoice_number,
            amount_due_cents, due_date
        ) VALUES (
            'inv_cascade', 'usr_cascade', 'sub_cascade', 'INV-CASC-001',
            4900, '2026-11-01 00:00:00'
        );
        """)
    db_conn.commit()

    # Delete the user
    cursor.execute("DELETE FROM users WHERE id = 'usr_cascade';")
    db_conn.commit()

    # Verify subscription was deleted via CASCADE
    cursor.execute("SELECT COUNT(*) FROM subscriptions WHERE id = 'sub_cascade';")
    assert cursor.fetchone()[0] == 0

    # Verify invoice was deleted via CASCADE
    cursor.execute("SELECT COUNT(*) FROM invoices WHERE id = 'inv_cascade';")
    assert cursor.fetchone()[0] == 0

    cursor.close()
