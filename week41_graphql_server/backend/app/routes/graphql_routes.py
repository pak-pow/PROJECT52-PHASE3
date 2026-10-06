from flask import Blueprint, Response, jsonify, request

from app.graphql.schema import execute_query, get_sdl

graphql_bp = Blueprint("graphql", __name__)


@graphql_bp.route("/graphql", methods=["POST"])
def graphql_endpoint():
    """
    Main GraphQL execution endpoint accepting query strings and optional variables.
    """
    data = request.get_json(silent=True) or {}
    query_str = data.get("query")
    variables = data.get("variables")

    if not query_str:
        return (
            jsonify(
                {"errors": [{"message": "Must provide query string in request body."}]}
            ),
            400,
        )

    result = execute_query(query_str, variables=variables)

    response_payload = {}
    if result.data is not None:
        response_payload["data"] = result.data

    if result.errors:
        response_payload["errors"] = [
            {"message": str(err.message)} for err in result.errors
        ]
        return jsonify(response_payload), 400 if result.data is None else 200

    return jsonify(response_payload), 200


@graphql_bp.route("/graphql/sdl", methods=["GET"])
def schema_sdl_endpoint():
    """Returns the compiled GraphQL Schema Definition Language (SDL) as plain text."""
    sdl_content = get_sdl()
    return Response(sdl_content, mimetype="text/plain; charset=utf-8")
