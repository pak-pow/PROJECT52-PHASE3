"""Client entity model and validation rules for PulseAuth."""

import json
import sqlite3
from typing import Any, Dict, List, Optional

from werkzeug.security import check_password_hash, generate_password_hash


class ClientModel:
    """Manages OAuth 2.0 / OIDC registered client applications."""

    @staticmethod
    def create(
        conn: sqlite3.Connection,
        client_id: str,
        client_name: str,
        client_type: str,
        redirect_uris: List[str],
        grant_types: List[str],
        scopes: List[str],
        client_secret: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Register a new OAuth 2.0 client application."""
        if client_type not in ("public", "confidential"):
            raise ValueError("client_type must be either 'public' or 'confidential'.")

        secret_hash = None
        if client_type == "confidential":
            if not client_secret:
                raise ValueError("Confidential clients require a client_secret.")
            secret_hash = generate_password_hash(client_secret, method="scrypt")

        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO clients (
                client_id, client_secret_hash, client_name, client_type,
                redirect_uris_json, grant_types_json, scopes_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                client_id.strip(),
                secret_hash,
                client_name.strip(),
                client_type,
                json.dumps(redirect_uris),
                json.dumps(grant_types),
                json.dumps(scopes),
            ),
        )
        conn.commit()
        return ClientModel.get_by_client_id(conn, client_id)  # type: ignore

    @staticmethod
    def get_by_client_id(
        conn: sqlite3.Connection, client_id: str
    ) -> Optional[Dict[str, Any]]:
        """Fetch client record and parse JSON collection fields."""
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, client_id, client_secret_hash, client_name, client_type,
                   redirect_uris_json, grant_types_json, scopes_json, created_at
            FROM clients WHERE client_id = ?
            """,
            (client_id,),
        )
        row = cur.fetchone()
        if not row:
            return None

        data = dict(row)
        data["redirect_uris"] = json.loads(data["redirect_uris_json"])
        data["grant_types"] = json.loads(data["grant_types_json"])
        data["scopes"] = json.loads(data["scopes_json"])
        return data

    @staticmethod
    def verify_secret(
        conn: sqlite3.Connection, client_id: str, client_secret: str
    ) -> bool:
        """Verify client secret for confidential clients."""
        client = ClientModel.get_by_client_id(conn, client_id)
        if not client:
            return False

        if client["client_type"] == "public":
            # Public clients do not authenticate via client_secret
            return True

        if not client["client_secret_hash"] or not client_secret:
            return False

        return check_password_hash(client["client_secret_hash"], client_secret)

    @staticmethod
    def validate_redirect_uri(
        conn: sqlite3.Connection, client_id: str, redirect_uri: str
    ) -> bool:
        """Validate redirect_uri strictly against registered URIs per RFC 6749."""
        client = ClientModel.get_by_client_id(conn, client_id)
        if not client:
            return False
        return redirect_uri in client.get("redirect_uris", [])

    @staticmethod
    def validate_scopes(
        conn: sqlite3.Connection, client_id: str, requested_scopes: List[str]
    ) -> bool:
        """Verify that all requested scopes are allowed for this client."""
        client = ClientModel.get_by_client_id(conn, client_id)
        if not client:
            return False
        allowed = set(client.get("scopes", []))
        return set(requested_scopes).issubset(allowed)

    @staticmethod
    def validate_grant_type(
        conn: sqlite3.Connection, client_id: str, grant_type: str
    ) -> bool:
        """Verify that client is authorized to execute requested grant_type."""
        client = ClientModel.get_by_client_id(conn, client_id)
        if not client:
            return False
        return grant_type in client.get("grant_types", [])

    @staticmethod
    def list_all(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
        """List all registered clients, omitting secret hashes."""
        cur = conn.cursor()
        cur.execute("""
            SELECT id, client_id, client_name, client_type,
                   redirect_uris_json, grant_types_json, scopes_json, created_at
            FROM clients ORDER BY created_at DESC
            """)
        clients = []
        for row in cur.fetchall():
            item = dict(row)
            item["redirect_uris"] = json.loads(item["redirect_uris_json"])
            item["grant_types"] = json.loads(item["grant_types_json"])
            item["scopes"] = json.loads(item["scopes_json"])
            clients.append(item)
        return clients
