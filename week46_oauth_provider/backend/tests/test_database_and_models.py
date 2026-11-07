"""Tests for database initialization, schema integrity, and entity models."""

import pytest

from app.db.connection import get_db
from app.models.client_model import ClientModel
from app.models.user_model import UserModel
from data.seed import seed_database


def test_user_model_crud_and_auth(app):
    """Verify user creation, password verification, and retrieval."""
    with app.app_context():
        conn = get_db(app.config["DATABASE_PATH"])

        # Create user
        user = UserModel.create(
            conn,
            email="test_user@example.com",
            password="SecurePass2026!",
            full_name="Test User",
        )
        assert user["id"] is not None
        assert user["email"] == "test_user@example.com"
        assert user["full_name"] == "Test User"
        assert user["is_active"] == 1

        # Retrieve by email
        fetched = UserModel.get_by_email(conn, "test_user@example.com")
        assert fetched is not None
        assert fetched["id"] == user["id"]

        # Retrieve by id
        fetched_id = UserModel.get_by_id(conn, user["id"])
        assert fetched_id is not None
        assert fetched_id["email"] == "test_user@example.com"

        # Successful auth
        auth_user = UserModel.verify_credentials(
            conn, "test_user@example.com", "SecurePass2026!"
        )
        assert auth_user is not None
        assert "password_hash" not in auth_user
        assert auth_user["email"] == "test_user@example.com"

        # Wrong password
        assert (
            UserModel.verify_credentials(
                conn, "test_user@example.com", "WrongPassword!"
            )
            is None
        )

        # Inactive user
        UserModel.create(
            conn,
            email="inactive@example.com",
            password="SecurePass2026!",
            full_name="Inactive User",
            is_active=False,
        )
        assert (
            UserModel.verify_credentials(
                conn, "inactive@example.com", "SecurePass2026!"
            )
            is None
        )

        # Non-existent email
        assert UserModel.get_by_email(conn, "missing@example.com") is None
        assert UserModel.get_by_id(conn, 999999) is None


def test_client_model_confidential(app):
    """Verify confidential client creation, secret verification, and policies."""
    with app.app_context():
        conn = get_db(app.config["DATABASE_PATH"])

        client = ClientModel.create(
            conn=conn,
            client_id="my-confidential-app",
            client_name="My Confidential App",
            client_type="confidential",
            client_secret="top_secret_code",
            redirect_uris=["https://example.com/callback", "https://app.com/cb"],
            grant_types=["authorization_code", "refresh_token"],
            scopes=["openid", "profile", "read:docs"],
        )

        assert client["client_id"] == "my-confidential-app"
        assert client["client_type"] == "confidential"
        assert len(client["redirect_uris"]) == 2

        # Verify secret
        assert ClientModel.verify_secret(conn, "my-confidential-app", "top_secret_code")
        assert not ClientModel.verify_secret(
            conn, "my-confidential-app", "wrong_secret"
        )
        assert not ClientModel.verify_secret(conn, "nonexistent", "top_secret_code")

        # Validate redirect URI exact matching
        assert ClientModel.validate_redirect_uri(
            conn, "my-confidential-app", "https://example.com/callback"
        )
        assert not ClientModel.validate_redirect_uri(
            conn, "my-confidential-app", "https://example.com/callback/extra"
        )
        assert not ClientModel.validate_redirect_uri(
            conn, "my-confidential-app", "https://malicious.com"
        )

        # Validate scopes
        assert ClientModel.validate_scopes(
            conn, "my-confidential-app", ["openid", "profile"]
        )
        assert not ClientModel.validate_scopes(
            conn, "my-confidential-app", ["openid", "admin:write"]
        )

        # Validate grant types
        assert ClientModel.validate_grant_type(
            conn, "my-confidential-app", "authorization_code"
        )
        assert not ClientModel.validate_grant_type(
            conn, "my-confidential-app", "client_credentials"
        )


def test_client_model_public(app):
    """Verify public client registration without client_secret."""
    with app.app_context():
        conn = get_db(app.config["DATABASE_PATH"])

        client = ClientModel.create(
            conn=conn,
            client_id="my-spa-app",
            client_name="Single Page App",
            client_type="public",
            redirect_uris=["http://localhost:3000/auth/callback"],
            grant_types=["authorization_code"],
            scopes=["openid", "profile"],
        )

        assert client["client_type"] == "public"
        assert client["client_secret_hash"] is None
        # Public client secret verification always passes without credentials
        assert ClientModel.verify_secret(conn, "my-spa-app", "")


def test_client_validation_errors(app):
    """Verify input validation errors for client creation."""
    with app.app_context():
        conn = get_db(app.config["DATABASE_PATH"])

        # Invalid client_type
        with pytest.raises(ValueError, match="client_type must be either"):
            ClientModel.create(conn, "bad", "Bad", "unknown", [], [], [])

        # Confidential without secret
        with pytest.raises(
            ValueError, match="Confidential clients require a client_secret"
        ):
            ClientModel.create(
                conn,
                "bad_conf",
                "Bad Conf",
                "confidential",
                [],
                [],
                [],
                client_secret=None,
            )


def test_database_seeding(app):
    """Verify database seeding creates users, clients, and is idempotent."""
    with app.app_context():
        db_path = app.config["DATABASE_PATH"]
        conn = seed_database(db_path)

        # Verify seeded users
        user = UserModel.get_by_email(conn, "developer@pulseauth.dev")
        assert user is not None
        assert UserModel.verify_credentials(
            conn, "developer@pulseauth.dev", "DevPass2026!"
        )

        # Verify seeded clients
        web_client = ClientModel.get_by_client_id(conn, "pulse-web-app")
        assert web_client is not None
        assert web_client["client_type"] == "confidential"

        mobile_client = ClientModel.get_by_client_id(conn, "pulse-mobile-app")
        assert mobile_client is not None
        assert mobile_client["client_type"] == "public"

        m2m_client = ClientModel.get_by_client_id(conn, "pulse-m2m-service")
        assert m2m_client is not None
        assert m2m_client["client_type"] == "confidential"

        # Listing all clients
        all_clients = ClientModel.list_all(conn)
        assert len(all_clients) >= 3

        # Run seed again to ensure idempotency
        conn2 = seed_database(db_path)
        assert len(ClientModel.list_all(conn2)) == len(all_clients)
