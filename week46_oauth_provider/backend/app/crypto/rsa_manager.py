"""Asymmetric RSA Keypair and JWKS Manager for PulseAuth.

Implements RFC 7517 (JSON Web Key / JWKS), RFC 7518 (JWA), and RFC 7519 (JWT)
cryptographic operations for asymmetric RS256 token issuance.
"""

import base64
import hashlib
from pathlib import Path
from typing import Any, Dict, Optional

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def int_to_base64url(val: int) -> str:
    """Encode an integer as an unpadded Base64urlUInt string per RFC 7518."""
    byte_length = (val.bit_length() + 7) // 8
    raw_bytes = val.to_bytes(byte_length, byteorder="big")
    return base64.urlsafe_b64encode(raw_bytes).decode("ascii").rstrip("=")


def base64url_to_int(encoded: str) -> int:
    """Decode an unpadded Base64urlUInt string back to an integer."""
    padding = "=" * ((4 - len(encoded) % 4) % 4)
    raw_bytes = base64.urlsafe_b64decode(encoded + padding)
    return int.from_bytes(raw_bytes, byteorder="big")


class RSAKeyManager:
    """Manages RSA 2048-bit keypairs, PEM serialization, JWKS, and RS256 signing."""

    def __init__(
        self,
        private_key_path: Optional[str] = None,
        public_key_path: Optional[str] = None,
        auto_generate: bool = True,
        key_size: int = 2048,
    ) -> None:
        self.private_key_path = Path(private_key_path) if private_key_path else None
        self.public_key_path = Path(public_key_path) if public_key_path else None
        self.key_size = key_size

        self._private_key: Optional[rsa.RSAPrivateKey] = None
        self._public_key: Optional[rsa.RSAPublicKey] = None
        self._kid: Optional[str] = None

        if (
            self.private_key_path
            and self.private_key_path.exists()
            and self.public_key_path
            and self.public_key_path.exists()
        ):
            self.load_from_disk(self.private_key_path, self.public_key_path)
        elif auto_generate:
            self.generate_keypair(key_size=self.key_size)
            if self.private_key_path and self.public_key_path:
                self.save_to_disk(self.private_key_path, self.public_key_path)

    @property
    def kid(self) -> str:
        """Deterministic Key ID derived from SHA-256 fingerprint of the public key."""
        if not self._kid:
            if not self._public_key:
                raise ValueError("Public key is not initialized.")
            pub_bytes = self.public_pem_bytes
            self._kid = hashlib.sha256(pub_bytes).hexdigest()[:16]
        return self._kid

    @property
    def private_key(self) -> rsa.RSAPrivateKey:
        """Active RSA private key."""
        if not self._private_key:
            raise ValueError("RSA private key has not been generated or loaded.")
        return self._private_key

    @property
    def public_key(self) -> rsa.RSAPublicKey:
        """Active RSA public key."""
        if not self._public_key:
            raise ValueError("RSA public key has not been generated or loaded.")
        return self._public_key

    @property
    def private_pem_bytes(self) -> bytes:
        """RSA private key encoded as PKCS8 PEM bytes."""
        return self.private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

    @property
    def public_pem_bytes(self) -> bytes:
        """RSA public key encoded as SPKI PEM bytes."""
        return self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

    def generate_keypair(self, key_size: int = 2048) -> None:
        """Generate a new RSA 2048-bit keypair."""
        self._private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=key_size,
        )
        self._public_key = self._private_key.public_key()
        self._kid = None

    def save_to_disk(self, private_path: Path, public_path: Path) -> None:
        """Persist private and public PEM files to filesystem."""
        private_path.parent.mkdir(parents=True, exist_ok=True)
        public_path.parent.mkdir(parents=True, exist_ok=True)

        with open(private_path, "wb") as f_priv:
            f_priv.write(self.private_pem_bytes)

        with open(public_path, "wb") as f_pub:
            f_pub.write(self.public_pem_bytes)

    def load_from_disk(self, private_path: Path, public_path: Path) -> None:
        """Load private and public PEM files from filesystem."""
        with open(private_path, "rb") as f_priv:
            self._private_key = serialization.load_pem_private_key(
                f_priv.read(),
                password=None,
            )
        with open(public_path, "rb") as f_pub:
            self._public_key = serialization.load_pem_public_key(f_pub.read())
        self._kid = None

    def get_jwk(self) -> Dict[str, str]:
        """Convert public key into an RFC 7517 JSON Web Key dictionary."""
        public_numbers = self.public_key.public_numbers()
        return {
            "kty": "RSA",
            "use": "sig",
            "alg": "RS256",
            "kid": self.kid,
            "n": int_to_base64url(public_numbers.n),
            "e": int_to_base64url(public_numbers.e),
        }

    def get_jwks(self) -> Dict[str, Any]:
        """Return full RFC 7517 JWKS dictionary with keys array."""
        return {"keys": [self.get_jwk()]}

    def sign_jwt(
        self,
        payload: Dict[str, Any],
        extra_headers: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Sign a dictionary payload with the private RSA key using RS256."""
        headers = {"kid": self.kid, "alg": "RS256"}
        if extra_headers:
            headers.update(extra_headers)

        token = jwt.encode(
            payload=payload,
            key=self.private_pem_bytes,
            algorithm="RS256",
            headers=headers,
        )
        return token

    def verify_jwt(
        self,
        token: str,
        audience: Optional[str] = None,
        issuer: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Verify an RS256 signed JWT using the public RSA key."""
        decode_options = options or {}
        if audience is None and "verify_aud" not in decode_options:
            decode_options["verify_aud"] = False

        decoded = jwt.decode(
            jwt=token,
            key=self.public_pem_bytes,
            algorithms=["RS256"],
            audience=audience,
            issuer=issuer,
            options=decode_options,
        )
        return decoded
