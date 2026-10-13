"""Document REST routes for PulsePad."""

from flask import Blueprint, jsonify

document_bp = Blueprint("documents", __name__)


@document_bp.route("/documents", methods=["GET"])
def list_documents():
    """List documents endpoint placeholder."""
    return jsonify({"documents": []}), 200
