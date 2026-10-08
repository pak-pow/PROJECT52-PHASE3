import time

from flask import Blueprint, Response, jsonify, request

from app.graphql.dataloaders import create_dataloaders
from app.graphql.protection import validate_query_safety
from app.graphql.schema import execute_query, get_sdl

graphql_bp = Blueprint("graphql", __name__)


@graphql_bp.route("/graphql", methods=["POST"])
def graphql_endpoint():
    """
    Main GraphQL execution endpoint with DataLoader caching, query safety,
    and performance metrics.
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

    # Validate query depth and complexity safety limits
    is_safe, error_msg, depth, complexity = validate_query_safety(query_str)
    if not is_safe:
        return (
            jsonify({"errors": [{"message": error_msg}]}),
            400,
        )

    start_time = time.perf_counter()
    dataloaders = create_dataloaders()
    context = {"dataloaders": dataloaders, "request": request}

    result = execute_query(query_str, variables=variables, context_value=context)

    duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
    response_payload = {}
    if result.data is not None:
        response_payload["data"] = result.data

    if result.errors:
        response_payload["errors"] = [
            {"message": str(err.message)} for err in result.errors
        ]

    response_payload["extensions"] = {
        "duration_ms": duration_ms,
        "depth": depth,
        "complexity": complexity,
        "dataloaders": dataloaders.get_stats(),
    }

    status_code = 400 if (result.data is None and result.errors) else 200
    res = jsonify(response_payload)
    res.headers["Server-Timing"] = f"gql;dur={duration_ms}"
    return res, status_code


@graphql_bp.route("/graphql/sdl", methods=["GET"])
def schema_sdl_endpoint():
    """Returns the compiled GraphQL Schema Definition Language (SDL) as plain text."""
    sdl_content = get_sdl()
    return Response(sdl_content, mimetype="text/plain; charset=utf-8")
