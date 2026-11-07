"""Unit tests for RSA Keypair Manager, JWKS, and RS256 token operations."""

import jwt
import pytest

from app.crypto.rsa_manager import (
    RSAKeyManager,
    base64url_to_int,
    int_to_base64url,
)


def test_base64url_int_conversion():
    """Verify RFC 7518 Base64urlUInt encoding and decoding."""
    # e = 65537 must encode to AQAB
    assert int_to_base64url(65537) == "AQAB"
    assert base64url_to_int("AQAB") == 65537

    # Large integer roundtrip
    num = 123456789012345678901234567890
    encoded = int_to_base64url(num)
    assert "=" not in encoded
    assert base64url_to_int(encoded) == num


def test_rsa_key_generation_and_properties(rsa_manager: RSAKeyManager):
    """Verify RSA keypair initialization, PEM exports, and Key ID derivation."""
    assert rsa_manager.private_key is not None
    assert rsa_manager.public_key is not None
    assert len(rsa_manager.kid) == 16
    assert b"BEGIN PRIVATE KEY" in rsa_manager.private_pem_bytes
    assert b"BEGIN PUBLIC KEY" in rsa_manager.public_pem_bytes


def test_rsa_save_and_reload(tmp_path):
    """Verify RSA keys can be persisted to disk and reloaded deterministically."""
    priv_file = tmp_path / "priv.pem"
    pub_file = tmp_path / "pub.pem"

    mgr1 = RSAKeyManager(
        private_key_path=str(priv_file),
        public_key_path=str(pub_file),
        auto_generate=True,
    )
    kid1 = mgr1.kid

    assert priv_file.exists()
    assert pub_file.exists()

    # Load with a second manager
    mgr2 = RSAKeyManager(
        private_key_path=str(priv_file),
        public_key_path=str(pub_file),
        auto_generate=False,
    )
    assert mgr2.kid == kid1
    assert mgr2.public_pem_bytes == mgr1.public_pem_bytes


def test_jwk_export_rfc7517(rsa_manager: RSAKeyManager):
    """Verify RFC 7517 JSON Web Key format and required attributes."""
    jwk = rsa_manager.get_jwk()
    assert jwk["kty"] == "RSA"
    assert jwk["use"] == "sig"
    assert jwk["alg"] == "RS256"
    assert jwk["kid"] == rsa_manager.kid
    assert jwk["e"] == "AQAB"
    assert len(jwk["n"]) > 50

    jwks = rsa_manager.get_jwks()
    assert "keys" in jwks
    assert len(jwks["keys"]) == 1
    assert jwks["keys"][0] == jwk


def test_sign_and_verify_jwt(rsa_manager: RSAKeyManager):
    """Verify RS256 token signing, header injection, and claim verification."""
    payload = {
        "sub": "user_42",
        "iss": "http://127.0.0.1:5000",
        "aud": "pulse-web-app",
        "scope": "openid profile email",
    }
    token = rsa_manager.sign_jwt(payload)
    assert isinstance(token, str)

    # Check unverified header has kid
    header = jwt.get_unverified_header(token)
    assert header["alg"] == "RS256"
    assert header["kid"] == rsa_manager.kid

    # Decode and verify
    claims = rsa_manager.verify_jwt(
        token, audience="pulse-web-app", issuer="http://127.0.0.1:5000"
    )
    assert claims["sub"] == "user_42"
    assert claims["scope"] == "openid profile email"


def test_verify_jwt_tampered_fails(rsa_manager: RSAKeyManager):
    """Verify tampered token signature fails verification."""
    payload = {"sub": "user_42", "role": "user"}
    token = rsa_manager.sign_jwt(payload)

    # Tamper with token payload part
    parts = token.split(".")
    tampered_token = f"{parts[0]}.eyJyZXBsYWNlZCI6InRydWUifQ.{parts[2]}"

    with pytest.raises(jwt.InvalidSignatureError):
        rsa_manager.verify_jwt(tampered_token)


def test_verify_jwt_different_key_fails(rsa_manager: RSAKeyManager, tmp_path):
    """Verify tokens signed by another key fail verification."""
    other_priv = tmp_path / "other_priv.pem"
    other_pub = tmp_path / "other_pub.pem"
    other_mgr = RSAKeyManager(
        private_key_path=str(other_priv),
        public_key_path=str(other_pub),
        auto_generate=True,
    )

    token = other_mgr.sign_jwt({"sub": "user_99"})

    with pytest.raises(jwt.InvalidSignatureError):
        rsa_manager.verify_jwt(token)


def test_uninitialized_rsa_manager_errors():
    """Verify exceptions when calling properties on uninitialized manager."""
    mgr = RSAKeyManager(auto_generate=False)
    with pytest.raises(ValueError, match="RSA private key has not been generated"):
        _ = mgr.private_key
    with pytest.raises(ValueError, match="RSA public key has not been generated"):
        _ = mgr.public_key
    with pytest.raises(ValueError, match="Public key is not initialized"):
        _ = mgr.kid
