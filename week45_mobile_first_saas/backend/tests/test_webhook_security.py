"""Unit tests for Stripe-compatible cryptographic HMAC-SHA256 signature verification."""

import time

import pytest

from app.billing.webhook_security import (
    WebhookSignatureVerificationError,
    generate_webhook_signature,
    verify_webhook_signature,
)

SECRET = "whsec_test_secret_key_123456"
PAYLOAD = '{"id": "evt_test_001", "type": "customer.subscription.updated"}'


def test_verify_valid_signature():
    """Verify that a correctly signed payload verifies successfully."""
    now = int(time.time())
    header = generate_webhook_signature(PAYLOAD, SECRET, timestamp=now)
    assert (
        verify_webhook_signature(PAYLOAD, header, SECRET, tolerance_seconds=300) is True
    )


def test_verify_missing_header_raises():
    """Verify missing header raises WebhookSignatureVerificationError."""
    with pytest.raises(
        WebhookSignatureVerificationError, match="Missing Stripe-Signature"
    ):
        verify_webhook_signature(PAYLOAD, "", SECRET)


def test_verify_malformed_header_missing_parts():
    """Verify header missing timestamp or signature raises error."""
    # Missing v1 signature
    with pytest.raises(WebhookSignatureVerificationError, match="No 'v1' signatures"):
        verify_webhook_signature(PAYLOAD, "t=123456", SECRET)

    # Missing timestamp
    with pytest.raises(
        WebhookSignatureVerificationError, match="Timestamp 't' not found"
    ):
        verify_webhook_signature(PAYLOAD, "v1=abc123", SECRET)

    # Invalid timestamp format
    with pytest.raises(WebhookSignatureVerificationError, match="Invalid timestamp"):
        verify_webhook_signature(PAYLOAD, "t=not_an_int,v1=abc", SECRET)


def test_verify_timestamp_out_of_tolerance():
    """Verify timestamp outside tolerance window is rejected."""
    now = int(time.time())
    stale_timestamp = now - 600  # 10 minutes ago
    header = generate_webhook_signature(PAYLOAD, SECRET, timestamp=stale_timestamp)

    with pytest.raises(WebhookSignatureVerificationError, match="tolerance window"):
        verify_webhook_signature(
            PAYLOAD, header, SECRET, tolerance_seconds=300, current_timestamp=now
        )


def test_verify_tampered_payload():
    """Verify that tampering with payload invalidates signature."""
    now = int(time.time())
    header = generate_webhook_signature(PAYLOAD, SECRET, timestamp=now)
    tampered_payload = '{"id": "evt_test_001", "type": "customer.subscription.deleted"}'

    with pytest.raises(WebhookSignatureVerificationError, match="does not match"):
        verify_webhook_signature(tampered_payload, header, SECRET)


def test_verify_wrong_secret():
    """Verify verifying with incorrect secret raises error."""
    now = int(time.time())
    header = generate_webhook_signature(PAYLOAD, "whsec_wrong_secret", timestamp=now)

    with pytest.raises(WebhookSignatureVerificationError, match="does not match"):
        verify_webhook_signature(PAYLOAD, header, SECRET)


def test_verify_multiple_signatures_rollover():
    """Verify support for multiple v1 signatures during secret rollover."""
    now = int(time.time())
    valid_header = generate_webhook_signature(PAYLOAD, SECRET, timestamp=now)
    sig_valid = valid_header.split("v1=")[1]
    composite_header = f"t={now},v1=bad_old_sig_123,v1={sig_valid}"

    assert verify_webhook_signature(PAYLOAD, composite_header, SECRET) is True
