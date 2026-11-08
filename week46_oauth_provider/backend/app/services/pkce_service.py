"""Proof Key for Code Exchange (PKCE) service implementing RFC 7636."""

import base64
import hashlib
import hmac
import re
import secrets
from typing import Tuple

# RFC 7636 Section 4.1: characters [A-Z], [a-z], [0-9], "-", ".", "_", "~"
PKCE_CHARSET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._~"
VERIFIER_REGEX = re.compile(r"^[A-Za-z0-9\-._~]{43,128}$")


class PKCEService:
    """Manages generation, hashing, and verification of PKCE verifiers."""

    @staticmethod
    def generate_verifier(length: int = 64) -> str:
        """Generate a cryptographically secure random code_verifier (43-128 chars)."""
        if not (43 <= length <= 128):
            raise ValueError("Verifier length must be between 43 and 128 characters.")
        return "".join(secrets.choice(PKCE_CHARSET) for _ in range(length))

    @staticmethod
    def compute_challenge(verifier: str, method: str = "S256") -> str:
        """Derive code_challenge from code_verifier using method ('S256' or 'plain')."""
        normalized_method = method.upper() if method else "S256"

        if normalized_method == "PLAIN":
            return verifier

        if normalized_method == "S256":
            digest = hashlib.sha256(verifier.encode("ascii")).digest()
            return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")

        raise ValueError(
            f"Unsupported code_challenge_method: {method}. Must be 'S256' or 'plain'."
        )

    @staticmethod
    def validate_verifier_syntax(verifier: str) -> Tuple[bool, str]:
        """Verify code_verifier syntax conforming to RFC 7636 Section 4.1."""
        if not verifier:
            return False, "code_verifier is missing."
        if len(verifier) < 43:
            return False, "code_verifier too short (minimum 43 characters)."
        if len(verifier) > 128:
            return False, "code_verifier too long (maximum 128 characters)."
        if not VERIFIER_REGEX.match(verifier):
            return (
                False,
                "code_verifier contains invalid characters. Must be [A-Za-z0-9-._~].",
            )
        return True, ""

    @staticmethod
    def verify(verifier: str, challenge: str, method: str = "S256") -> Tuple[bool, str]:
        """Verify code_verifier against stored challenge with timing-safe comparison."""
        valid_syntax, err = PKCEService.validate_verifier_syntax(verifier)
        if not valid_syntax:
            return False, err

        if not challenge:
            return False, "code_challenge is missing."

        try:
            expected_challenge = PKCEService.compute_challenge(verifier, method)
        except ValueError as ex:
            return False, str(ex)

        if not hmac.compare_digest(expected_challenge, challenge):
            return False, "PKCE verification failed: challenge does not match verifier."

        return True, ""
