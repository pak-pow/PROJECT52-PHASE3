"""Integration tests for route gatekeeping decorators."""

import pytest
from flask import Blueprint, jsonify

from app import create_app
from app.services.decorators import check_quota, require_entitlement
from data.seed import seed_demo_user

test_bp = Blueprint("test_bp", __name__, url_prefix="/api/test")


@test_bp.route("/pro-feature", methods=["GET"])
@require_entitlement("custom_domains")
def pro_feature_route():
    return jsonify({"success": True, "message": "Access granted to Pro feature."})


@test_bp.route("/enterprise-feature", methods=["GET"])
@require_entitlement("sso")
def enterprise_feature_route():
    return jsonify({"success": True, "message": "Access granted to Enterprise SSO."})


@test_bp.route("/metered-action", methods=["POST"])
@check_quota("monthly_api_calls", cost=5, record=True)
def metered_action_route():
    return jsonify({"success": True, "message": "Metered action executed."})


@test_bp.route("/tight-quota-action", methods=["POST"])
@check_quota("max_projects", cost=50, record=False)
def tight_quota_action_route():
    return jsonify({"success": True, "message": "Projects created."})


@pytest.fixture
def test_client(temp_db_path, db_conn):
    """Yield a test client with test_bp registered and demo user seeded."""
    seed_demo_user(db_conn)
    test_config = {
        "TESTING": True,
        "DEBUG": True,
        "DB_PATH": str(temp_db_path),
        "SECRET_KEY": "test_secret_key_pulse_2026",
        "WEBHOOK_SIGNING_SECRET": "whsec_test_mock_secret_2026",
    }
    test_app = create_app(config=test_config)
    test_app.register_blueprint(test_bp)
    return test_app.test_client()


def test_require_entitlement_granted(test_client):
    """Verify authorized user successfully accesses entitled route."""
    # Alice is on Pro tier, which includes 'custom_domains'
    response = test_client.get(
        "/api/test/pro-feature",
        headers={"X-User-ID": "usr_demo_alice"},
    )
    assert response.status_code == 200
    assert response.get_json()["success"] is True


def test_require_entitlement_denied(test_client):
    """Verify non-subscriber or unentitled tier receives 403 Forbidden."""
    # Free tier user lacks 'custom_domains'
    response = test_client.get(
        "/api/test/pro-feature",
        headers={"X-User-ID": "usr_free_user"},
    )
    assert response.status_code == 403
    data = response.get_json()
    assert data["error"] == "feature_not_entitled"
    assert data["feature"] == "custom_domains"
    assert data["upgrade_url"] == "/#plans"


def test_require_entitlement_denied_for_enterprise(test_client):
    """Verify Pro subscriber is blocked from Enterprise-only features."""
    response = test_client.get(
        "/api/test/enterprise-feature",
        headers={"X-User-ID": "usr_demo_alice"},
    )
    assert response.status_code == 403
    data = response.get_json()
    assert data["error"] == "feature_not_entitled"
    assert data["feature"] == "sso"


def test_check_quota_permitted_and_headers_injected(test_client):
    """Verify request within quota succeeds and transparent headers are injected."""
    response = test_client.post(
        "/api/test/metered-action",
        headers={"X-User-ID": "usr_demo_alice"},
    )
    assert response.status_code == 200
    assert response.get_json()["success"] is True
    assert "X-Quota-Limit" in response.headers
    assert "X-Quota-Remaining" in response.headers
    assert "X-Quota-Used" in response.headers


def test_check_quota_exceeded_returns_402(test_client):
    """Verify request exceeding quota returns 402 Payment Required."""
    # Free user has max_projects: 1. Requesting 50 projects fails.
    response = test_client.post(
        "/api/test/tight-quota-action",
        headers={"X-User-ID": "usr_free_user"},
    )
    assert response.status_code == 402
    data = response.get_json()
    assert data["error"] == "quota_exceeded"
    assert data["metric"] == "max_projects"
    assert data["limit"] == 1
    assert data["upgrade_url"] == "/#plans"
