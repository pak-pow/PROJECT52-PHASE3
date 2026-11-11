"""Integration tests for developer client management and registration endpoints."""

from app.db.connection import get_db
from app.models.client_model import ClientModel


def test_client_registration_confidential_and_public(client, app, seeded_db):
    """Verify dynamic client registration for confidential and public clients."""
    # 1. Register confidential client
    conf_payload = {
        "client_name": "Test Confidential App",
        "client_type": "confidential",
        "redirect_uris": ["https://app.example.com/callback"],
        "grant_types": ["authorization_code", "refresh_token"],
        "scopes": ["openid", "profile", "read:documents"],
    }
    resp_conf = client.post("/api/v1/clients", json=conf_payload)
    assert resp_conf.status_code == 201
    conf_data = resp_conf.get_json()["data"]
    assert conf_data["client_name"] == "Test Confidential App"
    assert conf_data["client_type"] == "confidential"
    assert "client_secret" in conf_data
    assert len(conf_data["client_secret"]) > 20
    assert "client_secret_hash" not in conf_data

    # 2. Register public client
    pub_payload = {
        "client_name": "Test Public SPA",
        "client_type": "public",
        "redirect_uris": ["https://spa.example.com/callback"],
        "grant_types": ["authorization_code"],
        "scopes": ["openid", "profile"],
    }
    resp_pub = client.post("/api/v1/clients", json=pub_payload)
    assert resp_pub.status_code == 201
    pub_data = resp_pub.get_json()["data"]
    assert pub_data["client_name"] == "Test Public SPA"
    assert pub_data["client_type"] == "public"
    assert "client_secret" not in pub_data or pub_data["client_secret"] is None


def test_client_registration_validation_errors(client, app, seeded_db):
    """Verify 400 Bad Request on invalid client registration payloads."""
    # Missing client_name
    resp_no_name = client.post(
        "/api/v1/clients",
        json={"client_type": "confidential"},
    )
    assert resp_no_name.status_code == 400
    assert resp_no_name.get_json()["error"] == "invalid_request"

    # Invalid client_type
    resp_bad_type = client.post(
        "/api/v1/clients",
        json={"client_name": "Bad App", "client_type": "invalid_type"},
    )
    assert resp_bad_type.status_code == 400
    assert resp_bad_type.get_json()["error"] == "invalid_request"


def test_list_and_get_clients(client, app, seeded_db):
    """Verify listing clients and retrieving individual client records."""
    # List all clients
    resp_list = client.get("/api/v1/clients")
    assert resp_list.status_code == 200
    list_data = resp_list.get_json()
    assert list_data["status"] == "success"
    assert list_data["count"] >= 3
    for c in list_data["data"]:
        assert "client_secret_hash" not in c

    # Get existing client
    resp_get = client.get("/api/v1/clients/pulse-web-app")
    assert resp_get.status_code == 200
    get_data = resp_get.get_json()
    assert get_data["data"]["client_id"] == "pulse-web-app"
    assert "client_secret_hash" not in get_data["data"]

    # Get nonexistent client
    resp_404 = client.get("/api/v1/clients/nonexistent-client-id")
    assert resp_404.status_code == 404
    assert resp_404.get_json()["error"] == "not_found"


def test_rotate_client_secret(client, app, seeded_db):
    """Verify rotating client secret for confidential clients."""
    # 1. Rotate for confidential client
    resp_rot = client.post("/api/v1/clients/pulse-web-app/rotate-secret")
    assert resp_rot.status_code == 200
    rot_data = resp_rot.get_json()
    new_secret = rot_data["client_secret"]
    assert new_secret != "pulse_web_secret_2026"

    # Verify new secret works in database
    with app.app_context():
        conn = get_db()
        assert ClientModel.verify_secret(conn, "pulse-web-app", new_secret) is True
        assert (
            ClientModel.verify_secret(conn, "pulse-web-app", "pulse_web_secret_2026")
            is False
        )

    # 2. Reject rotating for public client
    resp_pub = client.post("/api/v1/clients/pulse-mobile-app/rotate-secret")
    assert resp_pub.status_code == 400
    assert resp_pub.get_json()["error"] == "invalid_request"

    # 3. Nonexistent client
    resp_404 = client.post("/api/v1/clients/unknown-client/rotate-secret")
    assert resp_404.status_code == 404


def test_delete_client(client, app, seeded_db):
    """Verify deleting registered clients."""
    # Create client to delete
    reg_resp = client.post(
        "/api/v1/clients",
        json={"client_name": "Temporary Client", "client_type": "public"},
    )
    cid = reg_resp.get_json()["data"]["client_id"]

    # Delete client
    del_resp = client.delete(f"/api/v1/clients/{cid}")
    assert del_resp.status_code == 200
    assert del_resp.get_json()["status"] == "deleted"

    # Confirm it is gone
    get_resp = client.get(f"/api/v1/clients/{cid}")
    assert get_resp.status_code == 404

    # Delete nonexistent returns 404
    del_404 = client.delete("/api/v1/clients/unknown-client-xyz")
    assert del_404.status_code == 404
