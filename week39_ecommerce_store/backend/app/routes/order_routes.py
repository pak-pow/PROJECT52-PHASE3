from flask import Blueprint, jsonify, request

from app.models.order_model import OrderModel
from app.services.payment_service import get_payment_adapter

order_bp = Blueprint("orders", __name__, url_prefix="/api/v1")


@order_bp.route("/checkout/create-order", methods=["POST"])
def create_order():
    data = request.get_json(silent=True) or {}
    cart_token = data.get("cart_token") or request.headers.get("X-Cart-Token")
    email = data.get("customer_email")
    name = data.get("customer_name")
    address = data.get("shipping_address")

    if not cart_token:
        return (
            jsonify(
                {
                    "status": "error",
                    "code": "MISSING_CART_TOKEN",
                    "message": "Cart token is required.",
                }
            ),
            400,
        )

    if not email or "@" not in email:
        return (
            jsonify(
                {
                    "status": "error",
                    "code": "INVALID_EMAIL",
                    "message": "A valid customer_email is required.",
                }
            ),
            400,
        )

    if not name or not name.strip():
        return (
            jsonify(
                {
                    "status": "error",
                    "code": "INVALID_NAME",
                    "message": "Customer name is required.",
                }
            ),
            400,
        )

    if not address or not address.strip():
        return (
            jsonify(
                {
                    "status": "error",
                    "code": "INVALID_ADDRESS",
                    "message": "Shipping address is required.",
                }
            ),
            400,
        )

    success, err_msg, order = OrderModel.create_order(
        cart_token=cart_token,
        customer_email=email,
        customer_name=name,
        shipping_address=address,
    )

    if not success:
        code = "INSUFFICIENT_STOCK" if "stock" in (err_msg or "") else "ORDER_FAILED"
        status_code = 409 if code == "INSUFFICIENT_STOCK" else 400
        return (
            jsonify({"status": "error", "code": code, "message": err_msg}),
            status_code,
        )

    return jsonify({"status": "success", "data": order}), 201


@order_bp.route("/orders/<order_number>", methods=["GET"])
def get_order(order_number):
    order = OrderModel.get_by_order_number(order_number)
    if not order:
        return (
            jsonify(
                {
                    "status": "error",
                    "code": "ORDER_NOT_FOUND",
                    "message": f"Order '{order_number}' was not found.",
                }
            ),
            404,
        )
    return jsonify({"status": "success", "data": order}), 200


@order_bp.route("/orders/<order_number>/invoice", methods=["GET"])
def get_invoice(order_number):
    invoice = OrderModel.get_invoice(order_number)
    if not invoice:
        return (
            jsonify(
                {
                    "status": "error",
                    "code": "INVOICE_NOT_FOUND",
                    "message": f"Invoice for order '{order_number}' was not found.",
                }
            ),
            404,
        )
    return jsonify({"status": "success", "data": invoice}), 200


@order_bp.route("/checkout/simulate-payment", methods=["POST"])
def simulate_payment():
    data = request.get_json(silent=True) or {}
    payment_intent_id = data.get("payment_intent_id")
    scenario = data.get("scenario", "success")

    if not payment_intent_id:
        return (
            jsonify(
                {
                    "status": "error",
                    "code": "MISSING_INTENT_ID",
                    "message": "payment_intent_id is required.",
                }
            ),
            400,
        )

    order = OrderModel.get_by_payment_intent_id(payment_intent_id)
    if not order:
        return (
            jsonify(
                {
                    "status": "error",
                    "code": "ORDER_NOT_FOUND",
                    "message": "Order for payment intent was not found.",
                }
            ),
            404,
        )

    adapter = get_payment_adapter()
    simulated_event = adapter.simulate_payment(
        payment_intent_id=payment_intent_id,
        scenario=scenario,
        metadata={"order_number": order["order_number"]},
    )

    if scenario == "success":
        OrderModel.transition_status(order["order_number"], "paid")
    else:
        OrderModel.transition_status(order["order_number"], "cancelled")

    updated = OrderModel.get_by_order_number(order["order_number"])
    return (
        jsonify(
            {
                "status": "success",
                "simulated_event": simulated_event,
                "order": updated,
            }
        ),
        200,
    )
