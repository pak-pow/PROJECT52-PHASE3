-- PulseSub SQLite Database Schema
-- Version: 1.0.0
-- Configured for SQLite WAL mode and strict foreign keys

PRAGMA foreign_keys = ON;

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user' CHECK(role IN ('user', 'admin')),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Plans table
CREATE TABLE IF NOT EXISTS plans (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    tier TEXT NOT NULL CHECK(tier IN ('free', 'starter', 'pro', 'enterprise')),
    price_monthly_cents INTEGER NOT NULL DEFAULT 0 CHECK(price_monthly_cents >= 0),
    price_annual_cents INTEGER NOT NULL DEFAULT 0 CHECK(price_annual_cents >= 0),
    limits_json TEXT NOT NULL DEFAULT '{}',
    features_json TEXT NOT NULL DEFAULT '[]',
    is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0, 1)),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Subscriptions table
CREATE TABLE IF NOT EXISTS subscriptions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    plan_id TEXT NOT NULL REFERENCES plans(id),
    billing_interval TEXT NOT NULL DEFAULT 'monthly' CHECK(billing_interval IN ('monthly', 'annual')),
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('trialing', 'active', 'past_due', 'canceled', 'expired')),
    current_period_start TIMESTAMP NOT NULL,
    current_period_end TIMESTAMP NOT NULL,
    cancel_at_period_end INTEGER NOT NULL DEFAULT 0 CHECK(cancel_at_period_end IN (0, 1)),
    canceled_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Invoices table
CREATE TABLE IF NOT EXISTS invoices (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    subscription_id TEXT REFERENCES subscriptions(id) ON DELETE SET NULL,
    invoice_number TEXT UNIQUE NOT NULL,
    amount_due_cents INTEGER NOT NULL CHECK(amount_due_cents >= 0),
    amount_paid_cents INTEGER NOT NULL DEFAULT 0 CHECK(amount_paid_cents >= 0),
    currency TEXT NOT NULL DEFAULT 'usd',
    status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft', 'open', 'paid', 'uncollectible', 'void')),
    line_items_json TEXT NOT NULL DEFAULT '[]',
    payment_attempt_count INTEGER NOT NULL DEFAULT 0 CHECK(payment_attempt_count >= 0),
    due_date TIMESTAMP NOT NULL,
    paid_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Usage Records table
CREATE TABLE IF NOT EXISTS usage_records (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    subscription_id TEXT REFERENCES subscriptions(id) ON DELETE SET NULL,
    metric_key TEXT NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 1 CHECK(quantity > 0),
    idempotency_key TEXT UNIQUE,
    recorded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Webhook Events table (Stripe-compatible)
CREATE TABLE IF NOT EXISTS webhook_events (
    id TEXT PRIMARY KEY,
    event_id TEXT UNIQUE NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'processed', 'failed')),
    error_message TEXT,
    received_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_subscriptions_user ON subscriptions(user_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_status ON subscriptions(status);
CREATE INDEX IF NOT EXISTS idx_invoices_user ON invoices(user_id);
CREATE INDEX IF NOT EXISTS idx_invoices_sub ON invoices(subscription_id);
CREATE INDEX IF NOT EXISTS idx_invoices_status ON invoices(status);
CREATE INDEX IF NOT EXISTS idx_usage_user_metric ON usage_records(user_id, metric_key, recorded_at);
CREATE INDEX IF NOT EXISTS idx_webhook_events_id ON webhook_events(event_id);
CREATE INDEX IF NOT EXISTS idx_webhook_events_status ON webhook_events(status);
