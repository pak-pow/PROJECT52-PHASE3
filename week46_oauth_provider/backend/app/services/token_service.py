"""OAuth 2.0 and OpenID Connect token issuance and cryptographic verification."""

import secrets
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import jwt

from app.crypto.rsa_manager import RSAKeyManager
from app.models.token_model import TokenModel


class TokenService:
    """Issues RS256 JWT access tokens, OIDC ID tokens, and opaque refresh tokens."""

    @staticmethod
    def generate_access_token(
        rsa_manager: RSAKeyManager,
        issuer: str,
        client_id: str,
        scope: str,
        user_id: Optional[int] = None,
        ttl_seconds: int = 3600,
    ) -> Tuple[str, str, datetime]:
        """Sign and issue an asymmetric RS256 JWT access token."""
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=ttl_seconds)
        jti = uuid.uuid4().hex
        sub = str(user_id) if user_id is not None else client_id

        payload = {
            "iss": issuer,
            "sub": sub,
            "aud": client_id,
            "client_id": client_id,
            "scope": scope,
            "token_type": "Bearer",
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
            "jti": jti,
        }

        token = rsa_manager.sign_jwt(payload)
        return token, jti, expires_at

    @staticmethod
    def generate_id_token(
        rsa_manager: RSAKeyManager,
        issuer: str,
        client_id: str,
        user: Dict[str, Any],
        scope: str,
        nonce: Optional[str] = None,
        ttl_seconds: int = 3600,
    ) -> Tuple[str, datetime]:
        """Sign and issue an OpenID Connect Core 1.0 ID Token."""
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=ttl_seconds)
        scopes: List[str] = scope.split() if scope else []

        payload: Dict[str, Any] = {
            "iss": issuer,
            "sub": str(user["id"]),
            "aud": client_id,
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
            "auth_time": int(now.timestamp()),
        }

        if nonce:
            payload["nonce"] = nonce

        if "email" in scopes:
            payload["email"] = user.get("email")
            payload["email_verified"] = True

        if "profile" in scopes:
            payload["name"] = user.get("full_name")
            email = user.get("email", "")
            if email and "@" in email:
                payload["preferred_username"] = email.split("@")[0]

        token = rsa_manager.sign_jwt(payload)
        return token, expires_at

    @staticmethod
    def generate_refresh_token(
        ttl_seconds: int = 30 * 24 * 3600,
    ) -> Tuple[str, datetime]:
        """Generate a cryptographically secure opaque refresh token."""
        token = secrets.token_urlsafe(48)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        return token, expires_at

    @staticmethod
    def issue_tokens(
        conn: sqlite3.Connection,
        rsa_manager: RSAKeyManager,
        issuer: str,
        client_id: str,
        scope: str,
        user: Optional[Dict[str, Any]] = None,
        nonce: Optional[str] = None,
        access_token_ttl: int = 3600,
        id_token_ttl: int = 3600,
        refresh_token_ttl: int = 30 * 24 * 3600,
        token_family_id: Optional[str] = None,
        include_refresh: bool = False,
    ) -> Dict[str, Any]:
        """Issue, persist, and return RFC 6749 compliant token response payload."""
        family_id = token_family_id or uuid.uuid4().hex
        user_id = user["id"] if user else None
        requested_scopes = set(scope.split()) if scope else set()

        # 1. Access Token
        access_token, jti, acc_exp = TokenService.generate_access_token(
            rsa_manager=rsa_manager,
            issuer=issuer,
            client_id=client_id,
            scope=scope,
            user_id=user_id,
            ttl_seconds=access_token_ttl,
        )
        TokenModel.create(
            conn=conn,
            token_type="access_token",
            raw_token=access_token,
            client_id=client_id,
            scope=scope,
            expires_at=acc_exp,
            user_id=user_id,
            jti=jti,
            token_family_id=family_id,
        )

        response: Dict[str, Any] = {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": access_token_ttl,
            "scope": scope,
        }

        # 2. OIDC ID Token (if openid requested and user is present)
        if "openid" in requested_scopes and user is not None:
            id_token, id_exp = TokenService.generate_id_token(
                rsa_manager=rsa_manager,
                issuer=issuer,
                client_id=client_id,
                user=user,
                scope=scope,
                nonce=nonce,
                ttl_seconds=id_token_ttl,
            )
            TokenModel.create(
                conn=conn,
                token_type="id_token",
                raw_token=id_token,
                client_id=client_id,
                scope=scope,
                expires_at=id_exp,
                user_id=user_id,
                token_family_id=family_id,
            )
            response["id_token"] = id_token

        # 3. Refresh Token (if offline_access requested or explicitly required)
        should_issue_refresh = include_refresh or ("offline_access" in requested_scopes)
        if should_issue_refresh and user is not None:
            ref_token, ref_exp = TokenService.generate_refresh_token(
                ttl_seconds=refresh_token_ttl
            )
            TokenModel.create(
                conn=conn,
                token_type="refresh_token",
                raw_token=ref_token,
                client_id=client_id,
                scope=scope,
                expires_at=ref_exp,
                user_id=user_id,
                token_family_id=family_id,
            )
            response["refresh_token"] = ref_token

        return response

    @staticmethod
    def verify_access_token(
        conn: sqlite3.Connection,
        rsa_manager: RSAKeyManager,
        issuer: str,
        raw_token: str,
    ) -> Tuple[bool, Optional[Dict[str, Any]], Optional[Dict[str, Any]], str]:
        """Verify JWT signature, issuer, claims, and check database revocation."""
        # Check database validity first
        valid, db_record, err = TokenModel.is_valid(conn, raw_token)
        if not valid:
            return False, None, db_record, err

        try:
            payload = rsa_manager.verify_jwt(
                raw_token,
                issuer=issuer,
                options={"verify_signature": True, "verify_exp": True},
            )
            return True, payload, db_record, ""
        except jwt.ExpiredSignatureError:
            return False, None, db_record, "Access token has expired."
        except jwt.PyJWTError as exc:
            return False, None, db_record, f"Invalid token signature: {str(exc)}"
