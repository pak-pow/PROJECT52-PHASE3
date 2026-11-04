"""Unit tests for AuthService, password hashing, and bearer token signing."""

import pytest

from app.db.connection import get_db_connection, init_db
from app.services.auth_service import (
    AuthService,
    create_auth_token,
    hash_password,
    verify_auth_token,
    verify_password,
)


@pytest.fixture
def auth_conn(tmp_path):
    """Isolated SQLite connection for auth service testing."""
    db_file = tmp_path / "auth_test.db"
    init_db(db_path=db_file, seed_defaults=True)
    conn = get_db_connection(db_file)
    yield conn
    conn.close()


def test_password_hashing_and_verification():
    """Verify salted deterministic password hashing and constant-time match."""
    password = "SecurePassword123"
    hashed = hash_password(password)

    assert isinstance(hashed, str)
    assert len(hashed) == 64
    assert verify_password(password, hashed) is True
    assert verify_password("WrongPassword", hashed) is False


def test_token_creation_and_verification():
    """Verify bearer token creation, claim parsing, and integrity."""
    token = create_auth_token(
        user_id="usr_test_123",
        email="test@pulsesub.io",
        role="user",
        secret_key="test_secret",
        expires_in_seconds=3600,
    )
    assert token.startswith("pst_")

    claims = verify_auth_token(token, secret_key="test_secret")
    assert claims is not None
    assert claims["user_id"] == "usr_test_123"
    assert claims["email"] == "test@pulsesub.io"
    assert claims["role"] == "user"


def test_token_tampering_fails():
    """Verify modified bearer tokens or incorrect secrets are rejected."""
    token = create_auth_token(
        user_id="usr_test_123",
        email="test@pulsesub.io",
        secret_key="test_secret",
    )
    # Incorrect secret
    assert verify_auth_token(token, secret_key="different_secret") is None

    # Tampered payload
    tampered = token[:-2] + "xx"
    assert verify_auth_token(tampered, secret_key="test_secret") is None

    # Invalid token strings
    assert verify_auth_token("not_a_valid_token") is None
    assert verify_auth_token("pst_invalid") is None


def test_token_expiration():
    """Verify expired bearer tokens return None."""
    token = create_auth_token(
        user_id="usr_test_123",
        email="test@pulsesub.io",
        secret_key="test_secret",
        expires_in_seconds=-10,  # Expired in past
    )
    assert verify_auth_token(token, secret_key="test_secret") is None


def test_auth_service_registration_and_login(auth_conn):
    """Verify customer registration, duplicate prevention, and authentication."""
    service = AuthService(auth_conn)

    # 1. Register new user
    user, token = service.register_user(
        email="bob@pulsesub.io",
        password="BobPassword2026",
        full_name="Bob Builder",
    )
    assert user["id"].startswith("usr_")
    assert user["email"] == "bob@pulsesub.io"
    assert user["full_name"] == "Bob Builder"
    assert token.startswith("pst_")

    # 2. Duplicate registration fails
    with pytest.raises(ValueError, match="already registered"):
        service.register_user(
            email="bob@pulsesub.io",
            password="OtherPassword",
            full_name="Bob Clone",
        )

    # 3. Invalid inputs fail
    with pytest.raises(ValueError, match="valid email"):
        service.register_user("invalid_email", "Pass123", "Name")
    with pytest.raises(ValueError, match="at least 6"):
        service.register_user("valid@email.com", "123", "Name")
    with pytest.raises(ValueError, match="cannot be blank"):
        service.register_user("valid@email.com", "Password123", "   ")

    # 4. Successful login
    auth_res = service.authenticate_user("bob@pulsesub.io", "BobPassword2026")
    assert auth_res is not None
    auth_user, auth_token = auth_res
    assert auth_user["id"] == user["id"]
    assert auth_token.startswith("pst_")

    # 5. Invalid credentials login
    assert service.authenticate_user("bob@pulsesub.io", "WrongPass") is None
    assert service.authenticate_user("nonexistent@pulsesub.io", "Pass123") is None

    # 6. Get user by ID
    fetched = service.get_user_by_id(user["id"])
    assert fetched is not None
    assert fetched["email"] == "bob@pulsesub.io"
    assert service.get_user_by_id("nonexistent_id") is None
