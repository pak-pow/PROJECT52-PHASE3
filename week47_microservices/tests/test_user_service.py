"""Unit and integration tests for User & Identity Service."""

import pytest
from flask.testing import FlaskClient

from services.user.app import create_user_app
from shared.config import TestingConfig


@pytest.fixture
def user_client() -> FlaskClient:
    """Fixture providing a test client for an isolated in-memory User app."""
    app = create_user_app(config_class=TestingConfig, db_path=":memory:")
    return app.test_client()


def test_user_health_probe(user_client: FlaskClient) -> None:
    """Verify user service vitality probe."""
    res = user_client.get("/health")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "UP"
    assert data["service"] == "user-service"
    assert "instance_id" in data


def test_user_creation_and_retrieval(user_client: FlaskClient) -> None:
    """Verify user profile creation, address addition, and profile lookup."""
    # Create user
    res = user_client.post(
        "/api/v1/users",
        json={"email": "developer@pulsemesh.dev", "full_name": "Dev User"},
    )
    assert res.status_code == 201
    user = res.get_json()
    assert user["email"] == "developer@pulsemesh.dev"
    assert user["full_name"] == "Dev User"
    assert user["api_key"].startswith("pk_")
    user_id = user["id"]

    # Add shipping address
    addr_res = user_client.post(
        f"/api/v1/users/{user_id}/addresses",
        json={
            "street": "100 Microservice Way",
            "city": "Cloud City",
            "country": "US",
            "postal_code": "94105",
            "is_default": True,
        },
    )
    assert addr_res.status_code == 201
    addr = addr_res.get_json()
    assert addr["city"] == "Cloud City"
    assert addr["is_default"] == 1

    # Fetch user with addresses
    get_res = user_client.get(f"/api/v1/users/{user_id}")
    assert get_res.status_code == 200
    fetched = get_res.get_json()
    assert fetched["id"] == user_id
    assert len(fetched["addresses"]) == 1
    assert fetched["addresses"][0]["street"] == "100 Microservice Way"


def test_user_creation_validation_errors(user_client: FlaskClient) -> None:
    """Verify validation errors for duplicate emails and empty fields."""
    # Empty payload
    res = user_client.post(
        "/api/v1/users",
        data="invalid",
        content_type="text/plain",
    )
    assert res.status_code == 400

    # Missing email
    res = user_client.post(
        "/api/v1/users",
        json={"email": "", "full_name": "Alice"},
    )
    assert res.status_code == 400
    assert "Email cannot be empty" in res.get_json()["message"]

    # Valid creation
    user_client.post(
        "/api/v1/users",
        json={"email": "unique@pulsemesh.dev", "full_name": "Alice"},
    )

    # Duplicate email
    dup_res = user_client.post(
        "/api/v1/users",
        json={"email": "unique@pulsemesh.dev", "full_name": "Alice 2"},
    )
    assert dup_res.status_code == 400
    assert "already exists" in dup_res.get_json()["message"]


def test_user_list_and_pagination(user_client: FlaskClient) -> None:
    """Verify listing users with pagination."""
    for i in range(5):
        user_client.post(
            "/api/v1/users",
            json={"email": f"user{i}@test.com", "full_name": f"User {i}"},
        )

    res = user_client.get("/api/v1/users?limit=3&offset=0")
    assert res.status_code == 200
    data = res.get_json()
    assert data["count"] == 3


def test_user_authentication_flow(user_client: FlaskClient) -> None:
    """Verify API key authentication endpoint."""
    res = user_client.post(
        "/api/v1/users",
        json={"email": "auth@pulsemesh.dev", "full_name": "Auth User"},
    )
    api_key = res.get_json()["api_key"]

    # Missing API key
    bad_res = user_client.post("/api/v1/users/authenticate", json={})
    assert bad_res.status_code == 400

    # Invalid API key
    unauth_res = user_client.post(
        "/api/v1/users/authenticate", json={"api_key": "pk_invalid"}
    )
    assert unauth_res.status_code == 401

    # Valid authentication
    auth_res = user_client.post("/api/v1/users/authenticate", json={"api_key": api_key})
    assert auth_res.status_code == 200
    assert auth_res.get_json()["status"] == "authenticated"
    assert auth_res.get_json()["user"]["email"] == "auth@pulsemesh.dev"


def test_user_not_found(user_client: FlaskClient) -> None:
    """Verify 404 for unknown user ID."""
    res = user_client.get("/api/v1/users/usr_non_existent")
    assert res.status_code == 404


def test_add_address_invalid_user(user_client: FlaskClient) -> None:
    """Verify adding address to non-existent user returns 400."""
    res = user_client.post(
        "/api/v1/users/usr_unknown/addresses",
        json={"street": "Main", "city": "NYC", "country": "US", "postal_code": "10001"},
    )
    assert res.status_code == 400
    assert "does not exist" in res.get_json()["message"]

    # Non-dict address payload
    bad_addr = user_client.post(
        "/api/v1/users/usr_unknown/addresses",
        data="bad",
        content_type="text/plain",
    )
    assert bad_addr.status_code == 400
