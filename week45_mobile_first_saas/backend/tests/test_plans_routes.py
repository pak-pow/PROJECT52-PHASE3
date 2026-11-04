"""Integration tests for public plans HTTP API endpoints."""

import pytest

from app import create_app
from app.db.connection import init_db


@pytest.fixture
def client(tmp_path):
    """Create Flask test client with an isolated temporary SQLite database."""
    test_db = tmp_path / "test_plans.db"
    init_db(db_path=test_db, seed_defaults=True)

    app = create_app(
        {
            "TESTING": True,
            "DB_PATH": test_db,
        }
    )
    with app.test_client() as test_client:
        yield test_client


def test_list_plans_returns_all_active_tiers(client):
    """Verify listing plans returns the 4 default seeded tiers sorted by price."""
    res = client.get("/api/v1/plans")
    assert res.status_code == 200
    data = res.get_json()
    assert "plans" in data
    assert data["total"] == 4

    tiers = [p["tier"] for p in data["plans"]]
    assert tiers == ["free", "starter", "pro", "enterprise"]


def test_get_single_plan_found(client):
    """Verify retrieving a single plan by ID returns plan attributes."""
    res = client.get("/api/v1/plans/plan_pro")
    assert res.status_code == 200
    data = res.get_json()
    assert data["plan"]["id"] == "plan_pro"
    assert data["plan"]["name"] == "Pro"
    assert "custom_domains" in data["plan"]["features"]


def test_get_single_plan_not_found(client):
    """Verify querying an invalid plan ID returns 404."""
    res = client.get("/api/v1/plans/plan_nonexistent")
    assert res.status_code == 404
    data = res.get_json()
    assert data["error"] == "plan_not_found"
