"""Cryptographic HMAC-SHA256 signature verification for Stripe-compatible webhooks."""

import hashlib
import hmac
import time
from typing import Optional


class WebhookSignatureVerificationError(Exception):
    """Raised when an inbound webhook signature fails verification."""

    pass


def verify_webhook_signature(
    payload: str,
    signature_header: str,
    secret: str,
    tolerance_seconds: int = 300,
    current_timestamp: Optional[int] = None,
) -> bool:
    """Verify inbound Stripe-compatible webhook HMAC-SHA256 signature.

    Format expected: 't=<timestamp>,v1=<signature>' (or multiple v1 values).
    Signature is computed as HMAC-SHA256(secret, f"{t}.{payload}").
    """
    if not signature_header:
        raise WebhookSignatureVerificationError("Missing Stripe-Signature header.")

    # Parse header pairs: t=..., v1=...
    timestamp: Optional[int] = None
    signatures: list[str] = []

    pairs = signature_header.split(",")
    for pair in pairs:
        parts = pair.strip().split("=", 1)
        if len(parts) != 2:
            continue
        key, value = parts[0].strip(), parts[1].strip()
        if key == "t":
            try:
                timestamp = int(value)
            except ValueError:
                raise WebhookSignatureVerificationError(
                    f"Invalid timestamp in Stripe-Signature header: '{value}'"
                )
        elif key == "v1":
            signatures.append(value)

    if timestamp is None:
        raise WebhookSignatureVerificationError(
            "Timestamp 't' not found in Stripe-Signature header."
        )

    if not signatures:
        raise WebhookSignatureVerificationError(
            "No 'v1' signatures found in Stripe-Signature header."
        )

    # Tolerance / replay defense
    now = current_timestamp if current_timestamp is not None else int(time.time())
    if abs(now - timestamp) > tolerance_seconds:
        diff = abs(now - timestamp)
        raise WebhookSignatureVerificationError(
            f"Timestamp outside tolerance window ({diff}s > {tolerance_seconds}s)."
        )

    # Compute expected signature: HMAC-SHA256(secret, f"{timestamp}.{payload}")
    signed_payload = f"{timestamp}.{payload}".encode("utf-8")
    expected_signature = hmac.new(
        secret.encode("utf-8"),
        signed_payload,
        hashlib.sha256,
    ).hexdigest()

    # Constant-time comparison against any provided v1 signatures
    for sig in signatures:
        if hmac.compare_digest(expected_signature, sig):
            return True

    raise WebhookSignatureVerificationError(
        "Signature does not match expected cryptographic hash."
    )


def generate_webhook_signature(
    payload: str,
    secret: str,
    timestamp: Optional[int] = None,
) -> str:
    """Generate a valid Stripe-Signature header string for testing and simulation."""
    ts = timestamp if timestamp is not None else int(time.time())
    signed_payload = f"{ts}.{payload}".encode("utf-8")
    signature = hmac.new(
        secret.encode("utf-8"),
        signed_payload,
        hashlib.sha256,
    ).hexdigest()
    return f"t={ts},v1={signature}"
