"""Integration tests for Stripe webhook HTTP endpoints and security headers."""

import json
import time

from app.billing.webhook_security import generate_webhook_signature
from data.seed import seed_demo_user


def test_webhook_route_missing_signature(client):
    """Verify endpoint rejects requests without Stripe-Signature header."""
    response = client.post(
        "/api/v1/webhooks/stripe",
        data=json.dumps({"id": "evt_test_01", "type": "invoice.paid"}),
        content_type="application/json",
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == "missing_signature"


def test_webhook_route_invalid_signature(client):
    """Verify endpoint rejects requests with invalid or tampered signature."""
    payload = json.dumps({"id": "evt_test_01", "type": "invoice.paid"})
    response = client.post(
        "/api/v1/webhooks/stripe",
        data=payload,
        headers={"Stripe-Signature": "t=123456,v1=invalid_signature_hex"},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid_signature"


def test_webhook_route_valid_dispatch_and_audit(client, db_conn, app):
    """Verify valid signed webhook dispatches and audits into webhook_events."""
    seed_demo_user(db_conn)
    secret = app.config.get("WEBHOOK_SIGNING_SECRET")

    payload_dict = {
        "id": "evt_route_test_001",
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "id": "sub_demo_alice_pro",
                "cancel_at_period_end": True,
            }
        },
    }
    payload_str = json.dumps(payload_dict)
    sig_header = generate_webhook_signature(
        payload_str, secret, timestamp=int(time.time())
    )

    # First request: process event
    response1 = client.post(
        "/api/v1/webhooks/stripe",
        data=payload_str,
        headers={"Stripe-Signature": sig_header},
        content_type="application/json",
    )
    assert response1.status_code == 200
    assert response1.get_json()["status"] == "processed"

    # Second request: idempotent duplicate
    response2 = client.post(
        "/api/v1/webhooks/stripe",
        data=payload_str,
        headers={"Stripe-Signature": sig_header},
        content_type="application/json",
    )
    assert response2.status_code == 200
    assert response2.get_json()["status"] == "already_processed"

    # Audit query: GET /api/v1/webhooks/events
    audit_resp = client.get("/api/v1/webhooks/events?limit=10")
    assert audit_resp.status_code == 200
    events = audit_resp.get_json()["events"]
    assert any(e["event_id"] == "evt_route_test_001" for e in events)


def test_webhook_route_malformed_json(client, app):
    """Verify malformed JSON payload returns 400 invalid_payload."""
    secret = app.config.get("WEBHOOK_SIGNING_SECRET")
    malformed = "{ not a json }"
    sig = generate_webhook_signature(malformed, secret, timestamp=int(time.time()))

    response = client.post(
        "/api/v1/webhooks/stripe",
        data=malformed,
        headers={"Stripe-Signature": sig},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid_payload"


def test_webhook_route_missing_event_id_or_type(client, app):
    """Verify missing event attributes returns 400 invalid_event_structure."""
    secret = app.config.get("WEBHOOK_SIGNING_SECRET")
    incomplete = json.dumps({"data": {}})
    sig = generate_webhook_signature(incomplete, secret, timestamp=int(time.time()))

    response = client.post(
        "/api/v1/webhooks/stripe",
        data=incomplete,
        headers={"Stripe-Signature": sig},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid_event_structure"
