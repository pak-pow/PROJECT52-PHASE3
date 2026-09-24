import json
import uuid


class PaymentError(Exception):
    pass


class SignatureVerificationError(PaymentError):
    pass


class StripeMockAdapter:
    def create_payment_intent(self, amount_cents, currency="usd", metadata=None):
        if amount_cents <= 0:
            raise PaymentError("Amount must be greater than zero.")

        intent_id = f"pi_mock_{uuid.uuid4().hex[:16]}"
        secret = f"{intent_id}_secret_{uuid.uuid4().hex[:12]}"
        return {
            "id": intent_id,
            "client_secret": secret,
            "amount": amount_cents,
            "currency": currency.lower(),
            "status": "requires_payment_method",
            "metadata": metadata or {},
        }

    def verify_webhook_signature(self, payload, sig_header, secret):
        if not sig_header or sig_header == "invalid_sig":
            raise SignatureVerificationError("Invalid or missing webhook signature.")

        if isinstance(payload, bytes):
            payload_str = payload.decode("utf-8")
        else:
            payload_str = payload

        try:
            return json.loads(payload_str)
        except Exception as e:
            raise SignatureVerificationError(f"Malformed webhook payload: {e}")

    def simulate_payment(self, payment_intent_id, scenario="success", metadata=None):
        event_id = f"evt_mock_{uuid.uuid4().hex[:16]}"
        metadata = metadata or {}

        if scenario == "success":
            return {
                "id": event_id,
                "type": "payment_intent.succeeded",
                "data": {
                    "object": {
                        "id": payment_intent_id,
                        "status": "succeeded",
                        "metadata": metadata,
                    }
                },
            }

        failure_reasons = {
            "card_declined": "Your card was declined.",
            "insufficient_funds": "Your card has insufficient funds.",
            "expired_card": "Your card has expired.",
        }
        reason = failure_reasons.get(scenario, "Payment failed.")

        return {
            "id": event_id,
            "type": "payment_intent.payment_failed",
            "data": {
                "object": {
                    "id": payment_intent_id,
                    "status": "requires_payment_method",
                    "last_payment_error": {"message": reason, "code": scenario},
                    "metadata": metadata,
                }
            },
        }


def get_payment_adapter():
    # Production Stripe adapter could be instantiated here when key is set.
    # Defaulting to mock adapter for offline reliability and automated tests.
    return StripeMockAdapter()
