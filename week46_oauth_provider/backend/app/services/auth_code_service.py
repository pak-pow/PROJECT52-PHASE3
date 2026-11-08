"""Authorization code issuance and request validation service."""

import sqlite3
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

from app.models.auth_code_model import AuthCodeModel
from app.models.client_model import ClientModel


class AuthCodeService:
    """Coordinates OAuth 2.0 authorization code validation and issuance."""

    @staticmethod
    def build_redirect_url(base_redirect_uri: str, params: Dict[str, Any]) -> str:
        """Append parameters to base redirect URI preserving existing query parts."""
        parsed = urllib.parse.urlparse(base_redirect_uri)
        existing_queries = urllib.parse.parse_qsl(parsed.query)

        new_queries = []
        for k, v in params.items():
            if v is not None:
                new_queries.append((k, str(v)))

        combined = existing_queries + new_queries
        new_query_string = urllib.parse.urlencode(combined)

        return urllib.parse.urlunparse(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                parsed.params,
                new_query_string,
                parsed.fragment,
            )
        )

    @staticmethod
    def validate_request(
        conn: sqlite3.Connection,
        response_type: Optional[str],
        client_id: Optional[str],
        redirect_uri: Optional[str],
        scope: Optional[str],
        code_challenge: Optional[str] = None,
        code_challenge_method: Optional[str] = None,
    ) -> Tuple[bool, Optional[Dict[str, Any]], str, str]:
        """Validate OAuth 2.0 authorization parameters per RFC 6749 and RFC 7636.

        Returns (is_valid, client_dict, error_code, error_description).
        """
        if not client_id:
            return False, None, "invalid_request", "Missing client_id parameter."

        client = ClientModel.get_by_client_id(conn, client_id)
        if not client:
            return False, None, "invalid_client", f"Unknown client_id: {client_id}."

        if not redirect_uri:
            return False, client, "invalid_request", "Missing redirect_uri parameter."

        if not ClientModel.validate_redirect_uri(conn, client_id, redirect_uri):
            return (
                False,
                client,
                "invalid_request",
                f"Unregistered or invalid redirect_uri: {redirect_uri}.",
            )

        if not response_type:
            return False, client, "invalid_request", "Missing response_type parameter."

        if response_type != "code":
            return (
                False,
                client,
                "unsupported_response_type",
                f"Unsupported response_type: {response_type}. Must be 'code'.",
            )

        if not ClientModel.validate_grant_type(conn, client_id, "authorization_code"):
            return (
                False,
                client,
                "unauthorized_client",
                "Client is not authorized to use the authorization_code grant type.",
            )

        # Validate requested scopes
        requested_scopes: List[str] = scope.split() if scope else []
        if requested_scopes and not ClientModel.validate_scopes(
            conn, client_id, requested_scopes
        ):
            return (
                False,
                client,
                "invalid_scope",
                f"One or more requested scopes are unauthorized for client: {scope}.",
            )

        # RFC 7636 PKCE Enforcement
        is_public = client.get("client_type") == "public"
        if is_public and not code_challenge:
            return (
                False,
                client,
                "invalid_request",
                "Public clients must supply a code_challenge per RFC 7636 (PKCE).",
            )

        if code_challenge:
            method = (code_challenge_method or "S256").upper()
            if method not in ("S256", "PLAIN"):
                return (
                    False,
                    client,
                    "invalid_request",
                    (
                        f"Unsupported code_challenge_method: {code_challenge_method}. "
                        "Must be 'S256' or 'plain'."
                    ),
                )

        return True, client, "", ""

    @staticmethod
    def issue_code(
        conn: sqlite3.Connection,
        client_id: str,
        user_id: int,
        redirect_uri: str,
        scope: str,
        ttl_seconds: int = 60,
        code_challenge: Optional[str] = None,
        code_challenge_method: Optional[str] = None,
        nonce: Optional[str] = None,
        state: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], str]:
        """Issue authorization code record and build standard redirection URL."""
        code_record = AuthCodeModel.create(
            conn=conn,
            client_id=client_id,
            user_id=user_id,
            redirect_uri=redirect_uri,
            scope=scope,
            ttl_seconds=ttl_seconds,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            nonce=nonce,
        )

        redirect_params = {"code": code_record["code"]}
        if state is not None:
            redirect_params["state"] = state

        redirect_url = AuthCodeService.build_redirect_url(redirect_uri, redirect_params)
        return code_record, redirect_url
