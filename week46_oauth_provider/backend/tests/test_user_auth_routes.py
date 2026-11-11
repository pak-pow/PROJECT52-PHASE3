"""Integration tests for user authentication and registration API endpoints."""


def test_user_auth_login_success(client, app, seeded_db):
    """Verify POST /api/v1/auth/login with valid user credentials."""
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "developer@pulseauth.dev", "password": "DevPass2026!"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "success"
    assert data["user"]["email"] == "developer@pulseauth.dev"
    assert data["user"]["full_name"] == "Alice Dev"
    assert "password_hash" not in data["user"]


def test_user_auth_login_failures(client, app, seeded_db):
    """Verify 400 Bad Request on missing parameters and 401 on wrong password."""
    # Missing fields
    resp_missing = client.post(
        "/api/v1/auth/login",
        json={"email": "developer@pulseauth.dev"},
    )
    assert resp_missing.status_code == 400
    assert resp_missing.get_json()["error"] == "invalid_request"

    # Invalid password
    resp_wrong = client.post(
        "/api/v1/auth/login",
        json={"email": "developer@pulseauth.dev", "password": "WrongPassword!"},
    )
    assert resp_wrong.status_code == 401
    assert resp_wrong.get_json()["error"] == "invalid_credentials"

    # Nonexistent user
    resp_none = client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@pulseauth.dev", "password": "SomePassword!"},
    )
    assert resp_none.status_code == 401


def test_user_auth_register_success(client, app, seeded_db):
    """Verify POST /api/v1/auth/register with valid new user data."""
    payload = {
        "email": "eve@pulseauth.dev",
        "password": "EvePassword2026!",
        "full_name": "Eve Engineer",
    }
    resp = client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["status"] == "created"
    assert data["user"]["email"] == "eve@pulseauth.dev"
    assert data["user"]["full_name"] == "Eve Engineer"
    assert "password_hash" not in data["user"]

    # Verify user can immediately log in
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "eve@pulseauth.dev", "password": "EvePassword2026!"},
    )
    assert login_resp.status_code == 200


def test_user_auth_register_validation_and_conflict(client, app, seeded_db):
    """Verify 400 on invalid input and 409 on existing email registration."""
    # Missing fields
    resp_missing = client.post(
        "/api/v1/auth/register",
        json={"email": "test@test.com", "password": "password123"},
    )
    assert resp_missing.status_code == 400

    # Malformed email
    resp_bad_email = client.post(
        "/api/v1/auth/register",
        json={
            "email": "not-an-email",
            "password": "password123",
            "full_name": "Test",
        },
    )
    assert resp_bad_email.status_code == 400

    # Password too short (< 8 chars)
    resp_short_pwd = client.post(
        "/api/v1/auth/register",
        json={"email": "test@test.com", "password": "short", "full_name": "Test"},
    )
    assert resp_short_pwd.status_code == 400

    # Conflict on existing email
    resp_conflict = client.post(
        "/api/v1/auth/register",
        json={
            "email": "developer@pulseauth.dev",
            "password": "Password123!",
            "full_name": "Another Alice",
        },
    )
    assert resp_conflict.status_code == 409
    assert resp_conflict.get_json()["error"] == "conflict"


def test_user_auth_list_users(client, app, seeded_db):
    """Verify GET /api/v1/auth/users lists users without password hashes."""
    resp = client.get("/api/v1/auth/users")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "success"
    assert data["count"] >= 3
    for u in data["data"]:
        assert "password_hash" not in u
        assert "email" in u
        assert "full_name" in u
