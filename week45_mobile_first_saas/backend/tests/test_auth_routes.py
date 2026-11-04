"""Integration tests for authentication HTTP API endpoints."""

import pytest

from app import create_app
from app.db.connection import init_db
from data.seed import seed_demo_user


@pytest.fixture
def auth_client(tmp_path):
    """Create Flask test client with an isolated temporary SQLite database."""
    test_db = tmp_path / "test_auth.db"
    init_db(db_path=test_db, seed_defaults=True)

    # Seed demo user
    from app.db.connection import get_db_connection

    conn = get_db_connection(test_db)
    seed_demo_user(conn)
    conn.close()

    app = create_app(
        {
            "TESTING": True,
            "DB_PATH": test_db,
            "SECRET_KEY": "test_auth_secret_key",
        }
    )
    with app.test_client() as client:
        yield client


def test_register_route_success(auth_client):
    """Verify customer registration endpoint returns 201 and token."""
    res = auth_client.post(
        "/api/v1/auth/register",
        json={
            "email": "charlie@pulsesub.io",
            "password": "CharliePassword2026",
            "full_name": "Charlie Chaplin",
        },
    )
    assert res.status_code == 201
    data = res.get_json()
    assert "token" in data
    assert data["user"]["email"] == "charlie@pulsesub.io"
    assert data["user"]["full_name"] == "Charlie Chaplin"


def test_register_route_missing_fields(auth_client):
    """Verify registration with missing payload fields returns 400."""
    res = auth_client.post(
        "/api/v1/auth/register",
        json={"email": "incomplete@pulsesub.io"},
    )
    assert res.status_code == 400
    data = res.get_json()
    assert data["error"] == "invalid_payload"


def test_register_route_duplicate_email(auth_client):
    """Verify duplicate registration returns 409 Conflict."""
    res = auth_client.post(
        "/api/v1/auth/register",
        json={
            "email": "alice@pulsesub.io",  # Already seeded demo user
            "password": "AnotherPassword",
            "full_name": "Alice Duplicate",
        },
    )
    assert res.status_code == 409
    data = res.get_json()
    assert "already registered" in data["message"].lower()


def test_login_route_success(auth_client):
    """Verify login with correct credentials returns 200 and bearer token."""
    res = auth_client.post(
        "/api/v1/auth/login",
        json={
            "email": "alice@pulsesub.io",
            "password": "PulseSubSecret2026",
        },
    )
    assert res.status_code == 200
    data = res.get_json()
    assert "token" in data
    assert data["user"]["email"] == "alice@pulsesub.io"


def test_login_route_invalid_credentials(auth_client):
    """Verify login with incorrect password returns 401 Unauthorized."""
    res = auth_client.post(
        "/api/v1/auth/login",
        json={
            "email": "alice@pulsesub.io",
            "password": "WrongPassword",
        },
    )
    assert res.status_code == 401
    data = res.get_json()
    assert data["error"] == "invalid_credentials"


def test_me_route_authenticated(auth_client):
    """Verify /me profile endpoint with bearer token and X-User-ID header."""
    # First login to get a token
    login_res = auth_client.post(
        "/api/v1/auth/login",
        json={
            "email": "alice@pulsesub.io",
            "password": "PulseSubSecret2026",
        },
    )
    token = login_res.get_json()["token"]

    # Call /me with Bearer token
    res = auth_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["user"]["email"] == "alice@pulsesub.io"
    assert data["plan"]["tier"] == "pro"
    assert data["subscription"] is not None


def test_me_route_nonexistent_user(auth_client):
    """Verify /me returns 404 if user ID does not exist."""
    res = auth_client.get(
        "/api/v1/auth/me",
        headers={"X-User-ID": "usr_nonexistent_999"},
    )
    assert res.status_code == 404
    data = res.get_json()
    assert data["error"] == "user_not_found"
