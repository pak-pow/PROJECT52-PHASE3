"""Unit tests for user scope consent persistence and evaluation."""

from app.db.connection import get_db
from app.models.consent_model import ConsentModel


def test_consent_lifecycle(app, seeded_db):
    """Verify scope consent granting, evaluation, expansion, and revocation."""
    with app.app_context():
        conn = get_db()
        user_id = 1
        client_id = "pulse-web-app"

        # Initially no consent
        assert not ConsentModel.has_consent(conn, user_id, client_id, ["openid"])
        assert ConsentModel.get_consent(conn, user_id, client_id) is None

        # Grant consent for openid
        record = ConsentModel.grant_consent(conn, user_id, client_id, ["openid"])
        assert record is not None
        assert record["scopes"] == ["openid"]
        assert ConsentModel.has_consent(conn, user_id, client_id, ["openid"])
        assert not ConsentModel.has_consent(
            conn, user_id, client_id, ["openid", "profile"]
        )

        # Expand consent to include profile and email
        expanded = ConsentModel.grant_consent(
            conn, user_id, client_id, ["openid", "profile", "email"]
        )
        assert set(expanded["scopes"]) == {"openid", "profile", "email"}
        assert ConsentModel.has_consent(conn, user_id, client_id, ["openid", "profile"])
        assert ConsentModel.has_consent(
            conn, user_id, client_id, ["openid", "profile", "email"]
        )

        # Revoke consent
        revoked = ConsentModel.revoke_consent(conn, user_id, client_id)
        assert revoked is True
        assert not ConsentModel.has_consent(conn, user_id, client_id, ["openid"])
        assert ConsentModel.get_consent(conn, user_id, client_id) is None

        # Revoking non-existent consent returns False
        assert ConsentModel.revoke_consent(conn, user_id, "nonexistent") is False
