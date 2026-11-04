"""Integration tests for entitlements inspection and feature check routes."""

import pytest

from app import create_app
from app.db.connection import get_db_connection, init_db
from data.seed import seed_demo_user


@pytest.fixture
def ent_client(tmp_path):
    """Create Flask test client with an isolated temporary SQLite database."""
    test_db = tmp_path / "test_ent_routes.db"
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


def test_get_my_features_snapshot(ent_client):
    """Verify /my-features returns comprehensive entitlements, limits, and usage."""
    res = ent_client.get(
        "/api/v1/entitlements/my-features",
        headers={"X-User-ID": "usr_demo_alice"},
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["user_id"] == "usr_demo_alice"
    assert data["plan"]["tier"] == "pro"
    assert "custom_domains" in data["features"]
    assert "max_projects" in data["limits"]
    assert "usage_summary" in data


def test_check_feature_access(ent_client):
    """Verify /check endpoint confirms allowed vs disallowed boolean features."""
    # Alice on Pro tier has custom_domains
    res_allowed = ent_client.get(
        "/api/v1/entitlements/check?feature=custom_domains",
        headers={"X-User-ID": "usr_demo_alice"},
    )
    assert res_allowed.status_code == 200
    data_allowed = res_allowed.get_json()
    assert data_allowed["allowed"] is True
    assert data_allowed["feature"] == "custom_domains"

    # Alice does not have Enterprise SSO
    res_denied = ent_client.get(
        "/api/v1/entitlements/check?feature=sso",
        headers={"X-User-ID": "usr_demo_alice"},
    )
    assert res_denied.status_code == 200
    data_denied = res_denied.get_json()
    assert data_denied["allowed"] is False


def test_check_feature_missing_parameter(ent_client):
    """Verify /check without feature query parameter returns 400."""
    res = ent_client.get("/api/v1/entitlements/check")
    assert res.status_code == 400
    assert res.get_json()["error"] == "missing_parameter"
