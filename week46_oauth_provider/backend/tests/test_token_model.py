"""Unit tests for TokenModel persistence, lookup, expiration, and revocation."""

from datetime import datetime, timedelta, timezone

import pytest

from app.db.connection import get_db
from app.models.token_model import TokenModel


def test_token_creation_and_lookup(app, seeded_db):
    """Verify token creation, SHA-256 value hashing, and lookup by raw token."""
    with app.app_context():
        conn = get_db()
        raw_token = "raw_sample_access_token_value_12345"
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=1)

        record = TokenModel.create(
            conn=conn,
            token_type="access_token",
            raw_token=raw_token,
            client_id="pulse-web-app",
            scope="openid profile",
            expires_at=expires_at,
            user_id=1,
            jti="sample_jti_001",
            token_family_id="family_123",
        )

        assert record["id"] is not None
        assert record["token_type"] == "access_token"
        assert record["client_id"] == "pulse-web-app"
        assert record["user_id"] == 1
        assert record["jti"] == "sample_jti_001"
        assert record["revoked_at"] is None
        assert record["token_value_hash"] == TokenModel.hash_token(raw_token)

        # Lookup by hash
        by_hash = TokenModel.get_by_hash(conn, record["token_value_hash"])
        assert by_hash is not None
        assert by_hash["id"] == record["id"]

        # Lookup by raw token
        by_raw = TokenModel.get_by_raw_token(conn, raw_token)
        assert by_raw is not None
        assert by_raw["id"] == record["id"]

        # Lookup by jti
        by_jti = TokenModel.get_by_jti(conn, "sample_jti_001")
        assert by_jti is not None
        assert by_jti["id"] == record["id"]


def test_token_validation_lifecycle(app, seeded_db):
    """Verify valid token, expiration detection, and revocation behavior."""
    with app.app_context():
        conn = get_db()

        # 1. Valid active token
        raw_valid = "valid_token_test_123"
        now = datetime.now(timezone.utc)
        TokenModel.create(
            conn=conn,
            token_type="access_token",
            raw_token=raw_valid,
            client_id="pulse-web-app",
            scope="openid",
            expires_at=now + timedelta(minutes=30),
            user_id=1,
        )
        is_val, rec, err = TokenModel.is_valid(conn, raw_valid)
        assert is_val is True
        assert err == ""

        # 2. Revoked token
        revoked = TokenModel.revoke(conn, raw_valid)
        assert revoked is True
        is_val_rev, _, err_rev = TokenModel.is_valid(conn, raw_valid)
        assert is_val_rev is False
        assert "revoked" in err_rev.lower()

        # Second revoke returns False (already revoked)
        second_rev = TokenModel.revoke(conn, raw_valid)
        assert second_rev is False

        # 3. Expired token
        raw_expired = "expired_token_test_456"
        TokenModel.create(
            conn=conn,
            token_type="access_token",
            raw_token=raw_expired,
            client_id="pulse-web-app",
            scope="openid",
            expires_at=now - timedelta(seconds=10),
            user_id=1,
        )
        is_val_exp, _, err_exp = TokenModel.is_valid(conn, raw_expired)
        assert is_val_exp is False
        assert "expired" in err_exp.lower()

        # 4. Nonexistent token
        is_val_none, _, err_none = TokenModel.is_valid(conn, "nonexistent_token")
        assert is_val_none is False
        assert "not found" in err_none.lower()


def test_token_family_revocation(app, seeded_db):
    """Verify bulk revocation of all tokens in a family during compromise detection."""
    with app.app_context():
        conn = get_db()
        family_id = "compromised_family_999"
        now = datetime.now(timezone.utc)
        exp = now + timedelta(hours=1)

        # Create two tokens sharing family_id
        t1 = "token_family_access_1"
        t2 = "token_family_refresh_2"
        TokenModel.create(
            conn=conn,
            token_type="access_token",
            raw_token=t1,
            client_id="pulse-web-app",
            scope="openid",
            expires_at=exp,
            user_id=1,
            token_family_id=family_id,
        )
        TokenModel.create(
            conn=conn,
            token_type="refresh_token",
            raw_token=t2,
            client_id="pulse-web-app",
            scope="openid",
            expires_at=exp,
            user_id=1,
            token_family_id=family_id,
        )

        assert TokenModel.is_valid(conn, t1)[0] is True
        assert TokenModel.is_valid(conn, t2)[0] is True

        # Revoke whole family
        revoked_count = TokenModel.revoke_family(conn, family_id)
        assert revoked_count == 2

        assert TokenModel.is_valid(conn, t1)[0] is False
        assert TokenModel.is_valid(conn, t2)[0] is False

        # Empty family id returns 0
        assert TokenModel.revoke_family(conn, "") == 0

        # Retrieve family tokens
        family_tokens = TokenModel.get_family_tokens(conn, family_id)
        assert len(family_tokens) == 2
        assert TokenModel.get_family_tokens(conn, "") == []


def test_token_model_invalid_type_raises(app, seeded_db):
    """Verify invalid token_type raises ValueError."""
    with app.app_context():
        conn = get_db()
        with pytest.raises(ValueError, match="Invalid token_type"):
            TokenModel.create(
                conn=conn,
                token_type="invalid_type",
                raw_token="token_val",
                client_id="pulse-web-app",
                scope="openid",
                expires_at=datetime.now(timezone.utc),
            )


def test_token_model_datetime_and_find_token(app, seeded_db):
    """Verify parse_datetime parsing variants and find_token fallback behavior."""
    with app.app_context():
        conn = get_db()
        # Datetime parsing
        assert TokenModel.parse_datetime(None) is None
        assert TokenModel.parse_datetime("invalid-string") is None
        now_dt = datetime.now()
        parsed_dt = TokenModel.parse_datetime(now_dt)
        assert parsed_dt.tzinfo == timezone.utc

        # find_token
        assert TokenModel.find_token(conn, "") is None
        assert TokenModel.find_token(conn, "missing_raw_token") is None

        # Create token with jti
        now = datetime.now(timezone.utc)
        exp = now + timedelta(hours=1)
        rec = TokenModel.create(
            conn=conn,
            token_type="access_token",
            raw_token="known_raw_access_token_123",
            client_id="pulse-web-app",
            scope="openid",
            expires_at=exp,
            user_id=1,
            jti="sample_jti_456",
        )
        assert (
            TokenModel.find_token(conn, "known_raw_access_token_123")["id"] == rec["id"]
        )

        # revoke_by_hash
        assert TokenModel.revoke_by_hash(conn, rec["token_value_hash"]) is True
        # already revoked
        assert TokenModel.revoke_by_hash(conn, rec["token_value_hash"]) is False
