"""Discovery, JWKS, and health probe endpoints for PulseAuth."""

from flask import Blueprint, current_app, jsonify

discovery_bp = Blueprint("discovery", __name__)


@discovery_bp.route("/.well-known/jwks.json", methods=["GET"])
def jwks():
    """Distribute public signing keys via RFC 7517 JSON Web Key Set."""
    rsa_manager = current_app.extensions["rsa_manager"]
    return jsonify(rsa_manager.get_jwks()), 200


@discovery_bp.route("/.well-known/openid-configuration", methods=["GET"])
def openid_configuration():
    """Publish RFC 8414 / OIDC Core Discovery metadata document."""
    issuer = current_app.config.get("ISSUER", "http://127.0.0.1:5000")
    scopes = current_app.config.get("SUPPORTED_SCOPES", ["openid", "profile", "email"])

    config = {
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}/oauth/authorize",
        "token_endpoint": f"{issuer}/oauth/token",
        "userinfo_endpoint": f"{issuer}/oauth/userinfo",
        "jwks_uri": f"{issuer}/.well-known/jwks.json",
        "registration_endpoint": f"{issuer}/api/v1/clients",
        "scopes_supported": scopes,
        "response_types_supported": ["code"],
        "response_modes_supported": ["query"],
        "grant_types_supported": [
            "authorization_code",
            "client_credentials",
            "refresh_token",
        ],
        "token_endpoint_auth_methods_supported": [
            "client_secret_basic",
            "client_secret_post",
            "none",
        ],
        "revocation_endpoint": f"{issuer}/oauth/revoke",
        "revocation_endpoint_auth_methods_supported": [
            "client_secret_basic",
            "client_secret_post",
            "none",
        ],
        "introspection_endpoint": f"{issuer}/oauth/introspect",
        "introspection_endpoint_auth_methods_supported": [
            "client_secret_basic",
            "client_secret_post",
        ],
        "end_session_endpoint": f"{issuer}/oauth/logout",
        "code_challenge_methods_supported": ["S256", "plain"],
        "id_token_signing_alg_values_supported": ["RS256"],
        "subject_types_supported": ["public"],
        "claims_supported": [
            "sub",
            "iss",
            "aud",
            "exp",
            "iat",
            "auth_time",
            "nonce",
            "email",
            "email_verified",
            "name",
        ],
    }
    return jsonify(config), 200


@discovery_bp.route("/api/v1/health", methods=["GET"])
def health():
    """Service vitality probe reporting issuer and active signing Key ID."""
    rsa_manager = current_app.extensions.get("rsa_manager")
    kid = rsa_manager.kid if rsa_manager else None

    return (
        jsonify(
            {
                "status": "healthy",
                "service": "PulseAuth Identity Provider",
                "version": "1.0.0",
                "issuer": current_app.config.get("ISSUER"),
                "key_id": kid,
            }
        ),
        200,
    )
