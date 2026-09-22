from flask import Blueprint, jsonify, request

from app.models.product_model import ProductModel

product_bp = Blueprint("products", __name__, url_prefix="/api/v1")


@product_bp.route("/products", methods=["GET"])
def list_products():
    category = request.args.get("category")
    sort = request.args.get("sort")
    search = request.args.get("search")
    limit = request.args.get("limit", default=20)
    offset = request.args.get("offset", default=0)

    result = ProductModel.get_all(
        category=category,
        sort=sort,
        search=search,
        limit=limit,
        offset=offset,
    )

    return jsonify(
        {
            "status": "success",
            "data": result["items"],
            "pagination": {
                "total": result["total"],
                "limit": result["limit"],
                "offset": result["offset"],
            },
        }
    )


@product_bp.route("/products/<slug>", methods=["GET"])
def get_product(slug):
    product = ProductModel.get_by_slug(slug)
    if not product:
        return (
            jsonify(
                {
                    "status": "error",
                    "code": "PRODUCT_NOT_FOUND",
                    "message": f"Product with slug '{slug}' was not found.",
                }
            ),
            404,
        )

    return jsonify({"status": "success", "data": product})


@product_bp.route("/categories", methods=["GET"])
def list_categories():
    categories = ProductModel.get_categories()
    return jsonify({"status": "success", "data": categories})
