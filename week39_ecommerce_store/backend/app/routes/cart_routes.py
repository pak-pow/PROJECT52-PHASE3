from flask import Blueprint, jsonify, request

from app.models.cart_model import CartModel

cart_bp = Blueprint("cart", __name__, url_prefix="/api/v1/cart")


def _get_cart_token():
    token = request.headers.get("X-Cart-Token")
    if not token and request.is_json:
        data = request.get_json(silent=True) or {}
        token = data.get("cart_token")
    if not token:
        token = request.args.get("token")
    return token


@cart_bp.route("", methods=["GET"])
def get_cart():
    token = _get_cart_token()
    if not token:
        cart_info = CartModel.get_or_create()
        token = cart_info["token"]

    cart = CartModel.get_cart_by_token(token)
    if not cart:
        cart_info = CartModel.get_or_create(token=token)
        cart = CartModel.get_cart_by_token(cart_info["token"])

    response = jsonify({"status": "success", "data": cart})
    response.headers["X-Cart-Token"] = cart["token"]
    return response, 200


@cart_bp.route("/items", methods=["POST"])
def add_item():
    data = request.get_json(silent=True) or {}
    product_id = data.get("product_id")
    quantity = data.get("quantity", 1)

    if not isinstance(product_id, int):
        return (
            jsonify(
                {
                    "status": "error",
                    "code": "INVALID_PRODUCT_ID",
                    "message": "Valid integer product_id is required.",
                }
            ),
            400,
        )

    if not isinstance(quantity, int) or quantity <= 0:
        return (
            jsonify(
                {
                    "status": "error",
                    "code": "INVALID_QUANTITY",
                    "message": "Quantity must be a positive integer.",
                }
            ),
            400,
        )

    token = _get_cart_token()
    success, err_msg, cart = CartModel.add_item(token, product_id, quantity)
    if not success:
        code = (
            "INSUFFICIENT_STOCK" if "stock" in (err_msg or "") else "ITEM_UNAVAILABLE"
        )
        status_code = 409 if code == "INSUFFICIENT_STOCK" else 404
        return (
            jsonify({"status": "error", "code": code, "message": err_msg}),
            status_code,
        )

    response = jsonify({"status": "success", "data": cart})
    response.headers["X-Cart-Token"] = cart["token"]
    return response, 200


@cart_bp.route("/items/<int:product_id>", methods=["PATCH"])
def update_item(product_id):
    data = request.get_json(silent=True) or {}
    quantity = data.get("quantity")

    if not isinstance(quantity, int):
        return (
            jsonify(
                {
                    "status": "error",
                    "code": "INVALID_QUANTITY",
                    "message": "Integer quantity is required.",
                }
            ),
            400,
        )

    token = _get_cart_token()
    success, err_msg, cart = CartModel.update_quantity(token, product_id, quantity)
    if not success:
        return (
            jsonify(
                {
                    "status": "error",
                    "code": "INSUFFICIENT_STOCK",
                    "message": err_msg,
                }
            ),
            409,
        )

    response = jsonify({"status": "success", "data": cart})
    response.headers["X-Cart-Token"] = cart["token"]
    return response, 200


@cart_bp.route("/items/<int:product_id>", methods=["DELETE"])
def remove_item(product_id):
    token = _get_cart_token()
    _, _, cart = CartModel.remove_item(token, product_id)
    response = jsonify({"status": "success", "data": cart})
    response.headers["X-Cart-Token"] = cart["token"]
    return response, 200


@cart_bp.route("", methods=["DELETE"])
def clear_cart():
    token = _get_cart_token()
    _, _, cart = CartModel.clear_cart(token)
    response = jsonify({"status": "success", "data": cart})
    response.headers["X-Cart-Token"] = cart["token"]
    return response, 200


@cart_bp.route("/promo", methods=["POST"])
def apply_promo():
    data = request.get_json(silent=True) or {}
    promo_code = data.get("promo_code")

    if (
        not promo_code
        or not isinstance(promo_code, str)
        or not promo_code.strip()
        or len(promo_code.strip()) > 30
    ):
        return (
            jsonify(
                {
                    "status": "error",
                    "code": "INVALID_PROMO_CODE",
                    "message": (
                        "promo_code string is required and must not exceed 30 chars."
                    ),
                }
            ),
            400,
        )

    token = _get_cart_token()
    success, err_msg, cart = CartModel.apply_promo(token, promo_code)
    if not success:
        return (
            jsonify(
                {
                    "status": "error",
                    "code": "PROMO_NOT_APPLIED",
                    "message": err_msg,
                }
            ),
            400,
        )

    response = jsonify({"status": "success", "data": cart})
    response.headers["X-Cart-Token"] = cart["token"]
    return response, 200


@cart_bp.route("/promo", methods=["DELETE"])
def remove_promo():
    token = _get_cart_token()
    success, err_msg, cart = CartModel.remove_promo(token)
    if not success:
        return (
            jsonify(
                {
                    "status": "error",
                    "code": "CART_NOT_FOUND",
                    "message": err_msg,
                }
            ),
            404,
        )

    response = jsonify({"status": "success", "data": cart})
    response.headers["X-Cart-Token"] = cart["token"]
    return response, 200
