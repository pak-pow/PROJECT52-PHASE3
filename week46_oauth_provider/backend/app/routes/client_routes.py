"""Developer client management endpoints for dynamic client registration."""

import secrets
from typing import List

from flask import Blueprint, jsonify, request

from app.db.connection import get_db
from app.models.client_model import ClientModel

client_bp = Blueprint("clients", __name__)


@client_bp.route("/api/v1/clients", methods=["GET"])
def list_clients():
    """List all registered OAuth 2.0 clients (omitting sensitive hashes)."""
    conn = get_db()
    clients = ClientModel.list_all(conn)
    return jsonify({"status": "success", "count": len(clients), "data": clients}), 200


@client_bp.route("/api/v1/clients", methods=["POST"])
def register_client():
    """Register a new OAuth 2.0 client application (RFC 7591 / Developer Portal)."""
    conn = get_db()
    data = request.get_json(silent=True) or request.form or {}

    client_name = data.get("client_name")
    if not client_name or not client_name.strip():
        return (
            jsonify(
                {
                    "error": "invalid_request",
                    "error_description": "Missing required 'client_name' parameter.",
                }
            ),
            400,
        )

    client_type = data.get("client_type", "confidential")
    if client_type not in ("public", "confidential"):
        return (
            jsonify(
                {
                    "error": "invalid_request",
                    "error_description": (
                        "client_type must be either 'public' or 'confidential'."
                    ),
                }
            ),
            400,
        )

    redirect_uris: List[str] = data.get("redirect_uris", [])
    if isinstance(redirect_uris, str):
        redirect_uris = [u.strip() for u in redirect_uris.split(",") if u.strip()]

    grant_types: List[str] = data.get(
        "grant_types", ["authorization_code", "refresh_token"]
    )
    if isinstance(grant_types, str):
        grant_types = [g.strip() for g in grant_types.split(",") if g.strip()]

    scopes: List[str] = data.get(
        "scopes", ["openid", "profile", "email", "offline_access"]
    )
    if isinstance(scopes, str):
        scopes = [s.strip() for s in scopes.split() if s.strip()]

    client_id = f"pulse-{secrets.token_hex(6)}"
    client_secret = secrets.token_urlsafe(32) if client_type == "confidential" else None

    created_client = ClientModel.create(
        conn=conn,
        client_id=client_id,
        client_name=client_name.strip(),
        client_type=client_type,
        redirect_uris=redirect_uris,
        grant_types=grant_types,
        scopes=scopes,
        client_secret=client_secret,
    )

    response_data = dict(created_client)
    response_data.pop("client_secret_hash", None)
    if client_secret:
        response_data["client_secret"] = client_secret

    return (
        jsonify(
            {
                "status": "created",
                "message": "OAuth 2.0 client registered successfully.",
                "data": response_data,
            }
        ),
        201,
    )


@client_bp.route("/api/v1/clients/<client_id>", methods=["GET"])
def get_client(client_id: str):
    """Fetch details of a single registered client."""
    conn = get_db()
    client = ClientModel.get_by_client_id(conn, client_id)
    if not client:
        return (
            jsonify(
                {
                    "error": "not_found",
                    "error_description": f"Client '{client_id}' not found.",
                }
            ),
            404,
        )

    safe_client = dict(client)
    safe_client.pop("client_secret_hash", None)
    return jsonify({"status": "success", "data": safe_client}), 200


@client_bp.route("/api/v1/clients/<client_id>/rotate-secret", methods=["POST"])
def rotate_client_secret(client_id: str):
    """Rotate client secret for confidential clients."""
    conn = get_db()
    client = ClientModel.get_by_client_id(conn, client_id)
    if not client:
        return (
            jsonify(
                {
                    "error": "not_found",
                    "error_description": f"Client '{client_id}' not found.",
                }
            ),
            404,
        )

    if client["client_type"] != "confidential":
        return (
            jsonify(
                {
                    "error": "invalid_request",
                    "error_description": (
                        "Public clients do not possess client secrets."
                    ),
                }
            ),
            400,
        )

    new_secret = secrets.token_urlsafe(32)
    success = ClientModel.rotate_secret(conn, client_id, new_secret)
    if not success:
        return (
            jsonify(
                {
                    "error": "server_error",
                    "error_description": "Failed to update client secret.",
                }
            ),
            500,
        )

    return (
        jsonify(
            {
                "status": "success",
                "message": "Client secret rotated successfully.",
                "client_id": client_id,
                "client_secret": new_secret,
            }
        ),
        200,
    )


@client_bp.route("/api/v1/clients/<client_id>", methods=["DELETE"])
def delete_client(client_id: str):
    """Delete a registered client by identifier."""
    conn = get_db()
    client = ClientModel.get_by_client_id(conn, client_id)
    if not client:
        return (
            jsonify(
                {
                    "error": "not_found",
                    "error_description": f"Client '{client_id}' not found.",
                }
            ),
            404,
        )

    ClientModel.delete(conn, client_id)
    return (
        jsonify(
            {
                "status": "deleted",
                "message": f"Client '{client_id}' was removed.",
                "client_id": client_id,
            }
        ),
        200,
    )
