from flask import Blueprint, current_app, jsonify, request

from app.models.order_model import OrderModel
from app.models.webhook_event_model import WebhookEventModel
from app.services.payment_service import (
    SignatureVerificationError,
    get_payment_adapter,
)

webhook_bp = Blueprint("webhooks", __name__, url_prefix="/api/v1/webhooks")


@webhook_bp.route("/stripe", methods=["POST"])
def stripe_webhook():
    sig_header = request.headers.get("Stripe-Signature")
    webhook_secret = current_app.config.get("STRIPE_WEBHOOK_SECRET", "whsec_mock")
    payload = request.get_data()

    adapter = get_payment_adapter()

    try:
        event = adapter.verify_webhook_signature(
            payload,
            sig_header=sig_header,
            secret=webhook_secret,
        )
    except SignatureVerificationError as e:
        return (
            jsonify(
                {
                    "status": "error",
                    "code": "INVALID_SIGNATURE",
                    "message": str(e),
                }
            ),
            400,
        )

    event_id = event.get("id")
    event_type = event.get("type")

    if not event_id:
        return (
            jsonify(
                {
                    "status": "error",
                    "code": "MALFORMED_EVENT",
                    "message": "Missing event ID in webhook payload.",
                }
            ),
            400,
        )

    # Idempotency check: if event already processed, ignore safely
    if WebhookEventModel.is_processed(event_id):
        return (
            jsonify(
                {
                    "status": "ignored",
                    "reason": "duplicate_event",
                    "event_id": event_id,
                }
            ),
            200,
        )

    data_object = event.get("data", {}).get("object", {})
    intent_id = data_object.get("id")
    metadata = data_object.get("metadata", {})
    order_number = metadata.get("order_number")

    order = None
    if order_number:
        order = OrderModel.get_by_order_number(order_number)
    elif intent_id:
        order = OrderModel.get_by_payment_intent_id(intent_id)

    if order:
        if event_type == "payment_intent.succeeded":
            OrderModel.transition_status(order["order_number"], "paid")
        elif event_type == "payment_intent.payment_failed":
            OrderModel.transition_status(order["order_number"], "cancelled")

    WebhookEventModel.record_event(
        event_id=event_id,
        event_type=event_type,
        payload=event,
        status="processed",
    )

    return (
        jsonify(
            {
                "status": "processed",
                "event_id": event_id,
                "event_type": event_type,
            }
        ),
        200,
    )
