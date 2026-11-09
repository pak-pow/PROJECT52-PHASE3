"""Client authentication service implementing RFC 6749 Section 2.3."""

import base64
import sqlite3
from typing import Any, Dict, Optional, Tuple

from flask import Request

from app.models.client_model import ClientModel


class ClientAuthService:
    """Authenticates OAuth 2.0 clients via HTTP Basic or request body parameters."""

    @staticmethod
    def extract_credentials(
        req: Request,
    ) -> Tuple[Optional[str], Optional[str], str]:
        """Extract client_id and client_secret from Basic Auth header or body."""
        # 1. Check HTTP Basic Authentication Header
        auth_header = req.headers.get("Authorization")
        if auth_header and auth_header.startswith("Basic "):
            try:
                b64_creds = auth_header[6:].strip()
                decoded = base64.b64decode(b64_creds).decode("utf-8")
                if ":" in decoded:
                    cid, sec = decoded.split(":", 1)
                    return cid.strip(), sec.strip(), "basic"
                return None, None, "basic_malformed"
            except Exception:
                return None, None, "basic_malformed"

        # 2. Check Request Body (form-encoded or JSON)
        data = req.form or req.get_json(silent=True) or {}
        client_id = data.get("client_id")
        client_secret = data.get("client_secret")

        if client_id is not None:
            return (
                str(client_id).strip(),
                str(client_secret).strip() if client_secret is not None else None,
                "body",
            )

        return None, None, "none"

    @staticmethod
    def authenticate(
        conn: sqlite3.Connection,
        req: Request,
        allow_public: bool = True,
    ) -> Tuple[bool, Optional[Dict[str, Any]], str, str, int]:
        """Verify client identity and credentials per RFC 6749 Section 2.3.1.

        Returns (valid, client, error_code, error_description, http_status).
        """
        client_id, client_secret, method = ClientAuthService.extract_credentials(req)

        if method == "basic_malformed":
            return (
                False,
                None,
                "invalid_client",
                "Malformed HTTP Basic Authorization header.",
                401,
            )

        if not client_id:
            return (
                False,
                None,
                "invalid_client",
                "Missing client_id in request.",
                401 if method == "basic" else 400,
            )

        client = ClientModel.get_by_client_id(conn, client_id)
        if not client:
            return (
                False,
                None,
                "invalid_client",
                "Client not found or unapproved.",
                401,
            )

        client_type = client.get("client_type")

        # Public clients (SPA / Mobile)
        if client_type == "public":
            if not allow_public:
                return (
                    False,
                    client,
                    "unauthorized_client",
                    "Public clients are not permitted for this grant type.",
                    400,
                )
            if client_secret:
                return (
                    False,
                    client,
                    "invalid_client",
                    "Public clients must not supply a client_secret.",
                    401,
                )
            return True, client, "", "", 200

        # Confidential clients (Backend Services / Web Apps)
        if not client_secret:
            return (
                False,
                client,
                "invalid_client",
                "Confidential clients require client_secret authentication.",
                401,
            )

        if not ClientModel.verify_secret(conn, client_id, client_secret):
            return (
                False,
                client,
                "invalid_client",
                "Invalid client_secret credentials.",
                401,
            )

        return True, client, "", "", 200
