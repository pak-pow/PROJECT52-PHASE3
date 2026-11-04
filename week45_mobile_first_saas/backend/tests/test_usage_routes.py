"""Integration tests for metered resource consumption and usage summary routes."""

import pytest

from app import create_app
from app.db.connection import get_db_connection, init_db
from data.seed import seed_demo_user


@pytest.fixture
def usage_client(tmp_path):
    """Create Flask test client with an isolated temporary SQLite database."""
    test_db = tmp_path / "test_usage_routes.db"
    init_db(db_path=test_db, seed_defaults=True)

    conn = get_db_connection(test_db)
    seed_demo_user(conn)
    conn.close()

    app = create_app(
        {
            "TESTING": True,
            "DB_PATH": test_db,
        }
    )
    with app.test_client() as client:
        yield client


def test_record_usage_valid(usage_client):
    """Verify recording resource consumption injects transparent quota headers."""
    res = usage_client.post(
        "/api/v1/usage/record",
        headers={"X-User-ID": "usr_demo_alice"},
        json={
            "metric_key": "monthly_api_calls",
            "quantity": 25,
            "idempotency_key": "req_key_12345",
        },
    )
    assert res.status_code == 201
    data = res.get_json()
    assert data["record"]["metric_key"] == "monthly_api_calls"
    assert data["record"]["quantity"] == 25
    assert "quota_status" in data

    # Verify transparent quota headers
    assert "X-Quota-Limit" in res.headers
    assert "X-Quota-Used" in res.headers
    assert "X-Quota-Remaining" in res.headers
    assert "X-Quota-Alert" in res.headers


def test_record_usage_idempotent_duplicate(usage_client):
    """Verify duplicate idempotency key does not increment usage a second time."""
    idem_key = "req_duplicate_test_key"
    payload = {
        "metric_key": "monthly_api_calls",
        "quantity": 10,
        "idempotency_key": idem_key,
    }

    # First request
    res1 = usage_client.post(
        "/api/v1/usage/record",
        headers={"X-User-ID": "usr_demo_alice"},
        json=payload,
    )
    assert res1.status_code == 201
    used1 = int(res1.headers["X-Quota-Used"])

    # Second request with same idempotency key
    res2 = usage_client.post(
        "/api/v1/usage/record",
        headers={"X-User-ID": "usr_demo_alice"},
        json=payload,
    )
    assert res2.status_code == 201
    used2 = int(res2.headers["X-Quota-Used"])
    assert used1 == used2


def test_record_usage_validation_errors(usage_client):
    """Verify validation errors for missing metric or invalid quantity."""
    # Missing metric_key
    res_no_metric = usage_client.post(
        "/api/v1/usage/record",
        headers={"X-User-ID": "usr_demo_alice"},
        json={"quantity": 5},
    )
    assert res_no_metric.status_code == 400
    assert res_no_metric.get_json()["error"] == "invalid_payload"

    # Non-positive quantity
    res_bad_qty = usage_client.post(
        "/api/v1/usage/record",
        headers={"X-User-ID": "usr_demo_alice"},
        json={"metric_key": "storage_mb", "quantity": -5},
    )
    assert res_bad_qty.status_code == 400
    assert res_bad_qty.get_json()["error"] == "invalid_quantity"


def test_get_usage_summary(usage_client):
    """Verify /summary returns all tracked quotas and alert levels."""
    res = usage_client.get(
        "/api/v1/usage/summary",
        headers={"X-User-ID": "usr_demo_alice"},
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["user_id"] == "usr_demo_alice"
    assert data["plan_tier"] == "pro"
    assert "monthly_api_calls" in data["usage_summary"]
    assert "storage_mb" in data["usage_summary"]
