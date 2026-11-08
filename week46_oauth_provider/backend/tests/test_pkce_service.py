"""Unit tests for RFC 7636 Proof Key for Code Exchange (PKCE) service."""

import pytest

from app.services.pkce_service import PKCEService


def test_pkce_rfc7636_appendix_b_test_vector():
    """Verify exact match against official RFC 7636 Appendix B test vector."""
    # From RFC 7636 Appendix B:
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    expected_challenge = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"

    computed = PKCEService.compute_challenge(verifier, method="S256")
    assert computed == expected_challenge

    # Verification must succeed
    valid, err = PKCEService.verify(verifier, expected_challenge, method="S256")
    assert valid is True
    assert err == ""


def test_pkce_generate_verifier():
    """Verify automatic generation of high-entropy verifiers."""
    v1 = PKCEService.generate_verifier(43)
    assert len(v1) == 43
    valid, _ = PKCEService.validate_verifier_syntax(v1)
    assert valid is True

    v2 = PKCEService.generate_verifier(128)
    assert len(v2) == 128
    valid, _ = PKCEService.validate_verifier_syntax(v2)
    assert valid is True

    # Invalid lengths
    with pytest.raises(ValueError, match="Verifier length must be between 43 and 128"):
        PKCEService.generate_verifier(42)

    with pytest.raises(ValueError, match="Verifier length must be between 43 and 128"):
        PKCEService.generate_verifier(129)


def test_pkce_plain_method():
    """Verify RFC 7636 plain method challenge identity."""
    verifier = PKCEService.generate_verifier(50)
    challenge = PKCEService.compute_challenge(verifier, method="plain")
    assert challenge == verifier

    valid, err = PKCEService.verify(verifier, challenge, method="plain")
    assert valid is True
    assert err == ""


def test_pkce_syntax_validation():
    """Verify validation of syntax, length, and character set rules."""
    # Empty
    valid, err = PKCEService.validate_verifier_syntax("")
    assert not valid
    assert "missing" in err

    # Too short
    valid, err = PKCEService.validate_verifier_syntax(
        "short_verifier_less_than_43_chars"
    )
    assert not valid
    assert "too short" in err

    # Too long
    valid, err = PKCEService.validate_verifier_syntax("a" * 129)
    assert not valid
    assert "too long" in err

    # Invalid characters (e.g., spaces, symbols, plus sign)
    valid, err = PKCEService.validate_verifier_syntax("a" * 42 + " ")
    assert not valid
    assert "invalid characters" in err

    valid, err = PKCEService.validate_verifier_syntax("a" * 42 + "+")
    assert not valid
    assert "invalid characters" in err


def test_pkce_tampered_verifier_rejected():
    """Verify mismatched or modified verifier is rejected."""
    verifier = PKCEService.generate_verifier(64)
    challenge = PKCEService.compute_challenge(verifier, method="S256")

    tampered = verifier[:-1] + ("b" if verifier[-1] != "b" else "c")
    valid, err = PKCEService.verify(tampered, challenge, method="S256")
    assert valid is False
    assert "does not match" in err


def test_pkce_missing_challenge_rejected():
    """Verify missing challenge rejection."""
    verifier = PKCEService.generate_verifier(64)
    valid, err = PKCEService.verify(verifier, challenge="")
    assert valid is False
    assert "missing" in err


def test_pkce_unsupported_method():
    """Verify error on unsupported challenge method."""
    verifier = PKCEService.generate_verifier(64)
    with pytest.raises(ValueError, match="Unsupported code_challenge_method"):
        PKCEService.compute_challenge(verifier, method="MD5")

    valid, err = PKCEService.verify(verifier, "challenge", method="MD5")
    assert valid is False
    assert "Unsupported" in err
