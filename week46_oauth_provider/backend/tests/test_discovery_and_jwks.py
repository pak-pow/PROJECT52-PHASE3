"""Tests for RFC 8414 Discovery, RFC 7517 JWKS, and service health endpoints."""


def test_openid_configuration_endpoint(client):
    """Verify /.well-known/openid-configuration adheres to OIDC Discovery."""
    response = client.get("/.well-known/openid-configuration")
    assert response.status_code == 200
    data = response.get_json()

    # Core required fields per RFC 8414
    assert data["issuer"] == "http://127.0.0.1:5000"
    assert data["authorization_endpoint"] == "http://127.0.0.1:5000/oauth/authorize"
    assert data["token_endpoint"] == "http://127.0.0.1:5000/oauth/token"
    assert data["userinfo_endpoint"] == "http://127.0.0.1:5000/oauth/userinfo"
    assert data["jwks_uri"] == "http://127.0.0.1:5000/.well-known/jwks.json"

    # Supported features
    assert "authorization_code" in data["grant_types_supported"]
    assert "client_credentials" in data["grant_types_supported"]
    assert "refresh_token" in data["grant_types_supported"]
    assert "code" in data["response_types_supported"]
    assert "S256" in data["code_challenge_methods_supported"]
    assert "plain" in data["code_challenge_methods_supported"]
    assert "RS256" in data["id_token_signing_alg_values_supported"]
    assert "openid" in data["scopes_supported"]


def test_jwks_endpoint(client, app):
    """Verify /.well-known/jwks.json serves active RSA signing keys."""
    response = client.get("/.well-known/jwks.json")
    assert response.status_code == 200
    data = response.get_json()

    assert "keys" in data
    assert len(data["keys"]) == 1

    key = data["keys"][0]
    rsa_mgr = app.extensions["rsa_manager"]
    assert key["kty"] == "RSA"
    assert key["use"] == "sig"
    assert key["alg"] == "RS256"
    assert key["kid"] == rsa_mgr.kid
    assert key["e"] == "AQAB"
    assert "n" in key


def test_health_endpoint(client, app):
    """Verify /api/v1/health returns vitality and active key fingerprint."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.get_json()

    assert data["status"] == "healthy"
    assert data["service"] == "PulseAuth Identity Provider"
    assert data["version"] == "1.0.0"
    assert data["key_id"] == app.extensions["rsa_manager"].kid


def test_404_error_handler(client):
    """Verify unknown endpoints return standard RFC error JSON."""
    response = client.get("/nonexistent/endpoint")
    assert response.status_code == 404
    data = response.get_json()
    assert data["error"] == "not_found"
