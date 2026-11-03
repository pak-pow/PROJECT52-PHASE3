"""Stripe-compatible webhook ingestion and audit routes."""

import json

from flask import Blueprint, current_app, jsonify, request

from app.billing.webhook_dispatcher import WebhookDispatcher
from app.billing.webhook_security import (
    WebhookSignatureVerificationError,
    verify_webhook_signature,
)
from app.config.settings import Config
from app.db.connection import get_db_connection

webhooks_bp = Blueprint("webhooks", __name__, url_prefix="/api/v1/webhooks")


@webhooks_bp.route("/stripe", methods=["POST"])
def handle_stripe_webhook():
    """Ingest, cryptographically verify, and dispatch inbound Stripe webhook events."""
    signature_header = request.headers.get("Stripe-Signature")
    if not signature_header:
        return (
            jsonify(
                {
                    "error": "missing_signature",
                    "message": "Required 'Stripe-Signature' header is missing.",
                }
            ),
            400,
        )

    secret = current_app.config.get(
        "WEBHOOK_SIGNING_SECRET", Config.WEBHOOK_SIGNING_SECRET
    )
    tolerance = current_app.config.get(
        "WEBHOOK_TIMESTAMP_TOLERANCE_SECONDS",
        Config.WEBHOOK_TIMESTAMP_TOLERANCE_SECONDS,
    )
    raw_payload = request.get_data(as_text=True)

    # 1. Cryptographic HMAC-SHA256 signature and timestamp tolerance check
    try:
        verify_webhook_signature(
            payload=raw_payload,
            signature_header=signature_header,
            secret=secret,
            tolerance_seconds=tolerance,
        )
    except WebhookSignatureVerificationError as exc:
        return (
            jsonify(
                {
                    "error": "invalid_signature",
                    "message": str(exc),
                }
            ),
            400,
        )

    # 2. Parse event payload
    try:
        event_payload = json.loads(raw_payload)
    except (ValueError, TypeError) as exc:
        return (
            jsonify(
                {
                    "error": "invalid_payload",
                    "message": f"Malformed JSON: {str(exc)}",
                }
            ),
            400,
        )

    event_id = event_payload.get("id")
    event_type = event_payload.get("type")
    if not event_id or not event_type:
        return (
            jsonify(
                {
                    "error": "invalid_event_structure",
                    "message": "Event payload must include 'id' and 'type' attributes.",
                }
            ),
            400,
        )

    # 3. Dispatch to idempotent event handler
    db_path = current_app.config.get("DB_PATH", Config.DB_PATH)
    conn = get_db_connection(db_path)
    try:
        dispatcher = WebhookDispatcher(conn)
        result = dispatcher.dispatch(
            event_id=event_id,
            event_type=event_type,
            payload=event_payload,
        )
        return jsonify(result), 200
    finally:
        conn.close()


@webhooks_bp.route("/events", methods=["GET"])
def list_webhook_events():
    """Retrieve logged inbound webhook events for the Billing Sandbox console."""
    limit = min(50, int(request.args.get("limit", 20)))
    db_path = current_app.config.get("DB_PATH", Config.DB_PATH)
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM webhook_events
            ORDER BY received_at DESC
            LIMIT ?;
            """,
            (limit,),
        )
        rows = cursor.fetchall()
        cursor.close()

        events = []
        for r in rows:
            events.append(
                {
                    "id": r["id"],
                    "event_id": r["event_id"],
                    "event_type": r["event_type"],
                    "status": r["status"],
                    "error_message": r["error_message"],
                    "received_at": r["received_at"],
                    "processed_at": r["processed_at"],
                }
            )
        return jsonify({"events": events, "count": len(events)}), 200
    finally:
        conn.close()
