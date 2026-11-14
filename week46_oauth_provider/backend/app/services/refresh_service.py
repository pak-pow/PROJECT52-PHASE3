"""Refresh token rotation & reuse detection service (RFC 6749 Section 6)."""

import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from app.crypto.rsa_manager import RSAKeyManager
from app.models.token_model import TokenModel
from app.models.user_model import UserModel
from app.services.audit_service import AuditService
from app.services.token_service import TokenService


class RefreshTokenService:
    """Manages refresh token exchange, cryptographic rotation, and reuse detection."""

    @staticmethod
    def rotate_token(
        conn: sqlite3.Connection,
        rsa_manager: RSAKeyManager,
        issuer: str,
        client: Dict[str, Any],
        refresh_token: str,
        requested_scope: Optional[str] = None,
        ip_address: Optional[str] = None,
        access_token_ttl: int = 3600,
        id_token_ttl: int = 3600,
        refresh_token_ttl: int = 30 * 24 * 3600,
    ) -> Tuple[bool, Optional[Dict[str, Any]], str, str, int]:
        """
        Validate refresh token, rotate tokens, or detect reuse and invalidate family.

        Returns:
            Tuple of (success, token_bundle, error_code, error_description, http_status)
        """
        record = TokenModel.get_by_raw_token(conn, refresh_token)
        if not record or record.get("token_type") != "refresh_token":
            AuditService.log(
                conn=conn,
                event_type="token_refresh_failed",
                status="failure",
                client_id=client["client_id"],
                ip_address=ip_address,
                details={"reason": "Refresh token not found or invalid type"},
            )
            return (
                False,
                None,
                "invalid_grant",
                "Invalid refresh token.",
                400,
            )

        # Verify client matching
        if record["client_id"] != client["client_id"]:
            AuditService.log(
                conn=conn,
                event_type="token_refresh_failed",
                status="failure",
                client_id=client["client_id"],
                ip_address=ip_address,
                details={
                    "reason": "Client mismatch",
                    "expected": record["client_id"],
                },
            )
            return (
                False,
                None,
                "invalid_grant",
                "Refresh token was issued to a different client.",
                400,
            )

        # Refresh Token Reuse Detection
        if record.get("revoked_at") is not None:
            family_id = record.get("token_family_id")
            revoked_count = (
                TokenModel.revoke_family(conn, family_id) if family_id else 0
            )
            AuditService.log(
                conn=conn,
                event_type="token_reuse_detected",
                status="failure",
                client_id=client["client_id"],
                user_id=record.get("user_id"),
                ip_address=ip_address,
                details={
                    "family_id": family_id,
                    "tokens_revoked": revoked_count,
                    "reason": "Attempted reuse of already-revoked refresh token",
                },
            )
            return (
                False,
                None,
                "invalid_grant",
                "Refresh token has been revoked or reused.",
                400,
            )

        # Check expiration
        expires_at = TokenModel.parse_datetime(record.get("expires_at"))
        if expires_at and datetime.now(timezone.utc) > expires_at:
            AuditService.log(
                conn=conn,
                event_type="token_refresh_failed",
                status="failure",
                client_id=client["client_id"],
                ip_address=ip_address,
                details={"reason": "Refresh token has expired"},
            )
            return (
                False,
                None,
                "invalid_grant",
                "Refresh token has expired.",
                400,
            )

        # Scope validation (downscoping allowed, scope expansion forbidden)
        original_scopes = set(record["scope"].split()) if record.get("scope") else set()
        if requested_scope:
            req_scopes = set(requested_scope.split())
            if not req_scopes.issubset(original_scopes):
                return (
                    False,
                    None,
                    "invalid_scope",
                    "Requested scope exceeds original granted scope.",
                    400,
                )
            effective_scope = requested_scope
        else:
            effective_scope = record.get("scope", "")

        # Revoke the consumed refresh token
        TokenModel.revoke_by_hash(conn, record["token_value_hash"])

        # Fetch user profile if user_id is present
        user = (
            UserModel.get_by_id(conn, record["user_id"])
            if record.get("user_id")
            else None
        )

        # Issue newly rotated token bundle preserving family lineage
        new_tokens = TokenService.issue_tokens(
            conn=conn,
            rsa_manager=rsa_manager,
            issuer=issuer,
            client_id=client["client_id"],
            scope=effective_scope,
            user=user,
            token_family_id=record.get("token_family_id"),
            access_token_ttl=access_token_ttl,
            id_token_ttl=id_token_ttl,
            refresh_token_ttl=refresh_token_ttl,
            include_refresh=True,
            resource=record.get("resource"),
        )

        AuditService.log(
            conn=conn,
            event_type="token_refreshed",
            status="success",
            client_id=client["client_id"],
            user_id=record.get("user_id"),
            ip_address=ip_address,
            details={
                "family_id": record.get("token_family_id"),
                "scope": effective_scope,
            },
        )

        return True, new_tokens, "", "", 200
