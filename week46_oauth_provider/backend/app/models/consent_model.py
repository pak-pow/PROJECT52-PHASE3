"""Consent model managing user-granted scope authorizations for OAuth clients."""

import json
import sqlite3
from typing import Any, Dict, List, Optional


class ConsentModel:
    """Manages explicit user scope consents per client application."""

    @staticmethod
    def get_consent(
        conn: sqlite3.Connection, user_id: int, client_id: str
    ) -> Optional[Dict[str, Any]]:
        """Fetch consent record for a user and client pair."""
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, user_id, client_id, scopes_json, granted_at
            FROM consents WHERE user_id = ? AND client_id = ?
            """,
            (user_id, client_id),
        )
        row = cur.fetchone()
        if not row:
            return None

        data = dict(row)
        data["scopes"] = json.loads(data["scopes_json"])
        return data

    @staticmethod
    def has_consent(
        conn: sqlite3.Connection,
        user_id: int,
        client_id: str,
        requested_scopes: List[str],
    ) -> bool:
        """Check if user has already granted all requested scopes to client."""
        consent = ConsentModel.get_consent(conn, user_id, client_id)
        if not consent:
            return False

        granted = set(consent.get("scopes", []))
        return set(requested_scopes).issubset(granted)

    @staticmethod
    def grant_consent(
        conn: sqlite3.Connection,
        user_id: int,
        client_id: str,
        scopes: List[str],
    ) -> Dict[str, Any]:
        """Record or expand scope consent granted by a user to a client."""
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO consents (user_id, client_id, scopes_json, granted_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, client_id) DO UPDATE SET
                scopes_json = excluded.scopes_json,
                granted_at = CURRENT_TIMESTAMP
            """,
            (user_id, client_id, json.dumps(sorted(list(set(scopes))))),
        )
        conn.commit()
        return ConsentModel.get_consent(conn, user_id, client_id)  # type: ignore

    @staticmethod
    def revoke_consent(conn: sqlite3.Connection, user_id: int, client_id: str) -> bool:
        """Revoke a user's consent for a client."""
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM consents WHERE user_id = ? AND client_id = ?",
            (user_id, client_id),
        )
        conn.commit()
        return cur.rowcount > 0
