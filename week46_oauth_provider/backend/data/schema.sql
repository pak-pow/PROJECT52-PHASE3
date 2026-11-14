-- PulseAuth Relational Database Schema
-- Implements RFC 6749, RFC 7636, OIDC Core 1.0, RFC 7009, and RFC 7662

PRAGMA foreign_keys = ON;

-- 1. Users table
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- 2. Clients table (Public vs Confidential OAuth Clients)
CREATE TABLE IF NOT EXISTS clients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id TEXT NOT NULL UNIQUE,
    client_secret_hash TEXT,
    client_name TEXT NOT NULL,
    client_type TEXT NOT NULL CHECK(client_type IN ('public', 'confidential')),
    redirect_uris_json TEXT NOT NULL,
    grant_types_json TEXT NOT NULL,
    scopes_json TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_clients_client_id ON clients(client_id);

-- 3. Authorization Codes (RFC 6749 & RFC 7636 PKCE)
CREATE TABLE IF NOT EXISTS authorization_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    client_id TEXT NOT NULL REFERENCES clients(client_id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    redirect_uri TEXT NOT NULL,
    scope TEXT NOT NULL,
    code_challenge TEXT,
    code_challenge_method TEXT CHECK(code_challenge_method IN ('S256', 'plain') OR code_challenge_method IS NULL),
    nonce TEXT,
    resource TEXT,
    expires_at TIMESTAMP NOT NULL,
    used_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_auth_codes_code ON authorization_codes(code);
CREATE INDEX IF NOT EXISTS idx_auth_codes_client ON authorization_codes(client_id);

-- 4. Issued Tokens & Revocation (RFC 6749, RFC 7009 & RFC 7662)
CREATE TABLE IF NOT EXISTS tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token_type TEXT NOT NULL CHECK(token_type IN ('access_token', 'refresh_token', 'id_token')),
    token_value_hash TEXT NOT NULL UNIQUE,
    jti TEXT,
    client_id TEXT NOT NULL REFERENCES clients(client_id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    scope TEXT NOT NULL,
    resource TEXT,
    token_family_id TEXT,
    expires_at TIMESTAMP NOT NULL,
    revoked_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_tokens_value_hash ON tokens(token_value_hash);
CREATE INDEX IF NOT EXISTS idx_tokens_family_id ON tokens(token_family_id);
CREATE INDEX IF NOT EXISTS idx_tokens_client_user ON tokens(client_id, user_id);

-- 5. Consents (User Scope Grants for Third-Party Clients)
CREATE TABLE IF NOT EXISTS consents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    client_id TEXT NOT NULL REFERENCES clients(client_id) ON DELETE CASCADE,
    scopes_json TEXT NOT NULL,
    granted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, client_id)
);

CREATE INDEX IF NOT EXISTS idx_consents_user_client ON consents(user_id, client_id);

-- 6. Audit & Security Telemetry Logs
CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    client_id TEXT,
    user_id INTEGER,
    ip_address TEXT,
    status TEXT NOT NULL CHECK(status IN ('success', 'failure')),
    details_json TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_event ON audit_logs(event_type, created_at);
