import json

import pytest

from app.models.cart_model import CartModel
from app.models.order_model import OrderModel
from app.models.product_model import ProductModel
from app.services.payment_service import (
    PaymentError,
    SignatureVerificationError,
    get_payment_adapter,
)


def _create_test_cart_with_item(client, product_id=1, quantity=2):
    res = client.post(
        "/api/v1/cart/items",
        json={"product_id": product_id, "quantity": quantity},
    )
    assert res.status_code == 200
    token = res.headers["X-Cart-Token"]
    return token


def test_checkout_create_order_success(app, client):
    token = _create_test_cart_with_item(client, product_id=1, quantity=2)

    with app.app_context():
        init_prod = ProductModel.get_by_id(1)
        init_stock = init_prod["stock_quantity"]

    order_payload = {
        "cart_token": token,
        "customer_email": "developer@shoppulse.dev",
        "customer_name": "Dev User",
        "shipping_address": "404 Main St, Silicon Valley, CA 94025",
    }
    res = client.post("/api/v1/checkout/create-order", json=order_payload)
    assert res.status_code == 201
    body = res.get_json()
    assert body["status"] == "success"
    order = body["data"]

    assert order["order_number"].startswith("ORD-")
    assert order["status"] == "pending"
    assert order["customer_email"] == "developer@shoppulse.dev"
    assert "client_secret" in order
    assert len(order["items"]) == 1
    assert order["items"][0]["quantity"] == 2

    # Verify inventory was decremented atomically
    with app.app_context():
        updated_prod = ProductModel.get_by_id(1)
        assert updated_prod["stock_quantity"] == init_stock - 2

    # Verify cart was cleared
    res_cart = client.get("/api/v1/cart", headers={"X-Cart-Token": token})
    assert res_cart.get_json()["data"]["items"] == []


def test_checkout_empty_cart_fails(client):
    res = client.post(
        "/api/v1/checkout/create-order",
        json={
            "cart_token": "nonexistent_token_123",
            "customer_email": "test@shoppulse.dev",
            "customer_name": "Test User",
            "shipping_address": "123 Street",
        },
    )
    assert res.status_code == 400


def test_checkout_validation_errors(client):
    token = _create_test_cart_with_item(client, product_id=1, quantity=1)

    # Missing email
    r1 = client.post(
        "/api/v1/checkout/create-order",
        json={
            "cart_token": token,
            "customer_name": "Dev",
            "shipping_address": "123 St",
        },
    )
    assert r1.status_code == 400
    assert r1.get_json()["code"] == "INVALID_EMAIL"

    # Missing name
    r2 = client.post(
        "/api/v1/checkout/create-order",
        json={
            "cart_token": token,
            "customer_email": "dev@test.com",
            "shipping_address": "123 St",
        },
    )
    assert r2.status_code == 400
    assert r2.get_json()["code"] == "INVALID_NAME"

    # Missing address
    r3 = client.post(
        "/api/v1/checkout/create-order",
        json={
            "cart_token": token,
            "customer_email": "dev@test.com",
            "customer_name": "Dev",
        },
    )
    assert r3.status_code == 400
    assert r3.get_json()["code"] == "INVALID_ADDRESS"

    # Missing cart token
    r4 = client.post(
        "/api/v1/checkout/create-order",
        json={
            "customer_email": "dev@test.com",
            "customer_name": "Dev",
            "shipping_address": "123 St",
        },
    )
    assert r4.status_code == 400
    assert r4.get_json()["code"] == "MISSING_CART_TOKEN"


def test_get_order_and_invoice(client):
    token = _create_test_cart_with_item(client, product_id=11, quantity=1)
    res_order = client.post(
        "/api/v1/checkout/create-order",
        json={
            "cart_token": token,
            "customer_email": "alex@shoppulse.dev",
            "customer_name": "Alex Mercer",
            "shipping_address": "101 Code Way",
        },
    )
    order_num = res_order.get_json()["data"]["order_number"]

    # Get order
    res_get = client.get(f"/api/v1/orders/{order_num}")
    assert res_get.status_code == 200
    assert res_get.get_json()["data"]["order_number"] == order_num

    # Get non-existent order
    res_bad = client.get("/api/v1/orders/ORD-NONEXISTENT")
    assert res_bad.status_code == 404

    # Get invoice
    res_inv = client.get(f"/api/v1/orders/{order_num}/invoice")
    assert res_inv.status_code == 200
    inv = res_inv.get_json()["data"]
    assert inv["order_number"] == order_num
    assert inv["invoice_number"].startswith("INV-")
    assert inv["customer"]["name"] == "Alex Mercer"

    # Non-existent invoice
    res_bad_inv = client.get("/api/v1/orders/ORD-NONEXISTENT/invoice")
    assert res_bad_inv.status_code == 404


def test_webhook_payment_succeeded(app, client):
    token = _create_test_cart_with_item(client, product_id=2, quantity=1)
    res_order = client.post(
        "/api/v1/checkout/create-order",
        json={
            "cart_token": token,
            "customer_email": "buyer@shoppulse.dev",
            "customer_name": "Buyer",
            "shipping_address": "777 Market St",
        },
    )
    order = res_order.get_json()["data"]
    order_num = order["order_number"]
    intent_id = order["payment_intent_id"]

    webhook_payload = {
        "id": "evt_test_success_123",
        "type": "payment_intent.succeeded",
        "data": {
            "object": {
                "id": intent_id,
                "metadata": {"order_number": order_num},
            }
        },
    }

    res_hook = client.post(
        "/api/v1/webhooks/stripe",
        data=json.dumps(webhook_payload),
        headers={"Content-Type": "application/json", "Stripe-Signature": "valid_sig"},
    )
    assert res_hook.status_code == 200
    assert res_hook.get_json()["status"] == "processed"

    # Verify order is now paid
    with app.app_context():
        order_updated = OrderModel.get_by_order_number(order_num)
        assert order_updated["status"] == "paid"


def test_webhook_idempotency(client):
    token = _create_test_cart_with_item(client, product_id=2, quantity=1)
    res_order = client.post(
        "/api/v1/checkout/create-order",
        json={
            "cart_token": token,
            "customer_email": "buyer@shoppulse.dev",
            "customer_name": "Buyer",
            "shipping_address": "777 Market St",
        },
    )
    order = res_order.get_json()["data"]
    order_num = order["order_number"]
    intent_id = order["payment_intent_id"]

    webhook_payload = {
        "id": "evt_idempotency_test_999",
        "type": "payment_intent.succeeded",
        "data": {
            "object": {
                "id": intent_id,
                "metadata": {"order_number": order_num},
            }
        },
    }

    # First delivery
    r1 = client.post(
        "/api/v1/webhooks/stripe",
        data=json.dumps(webhook_payload),
        headers={"Content-Type": "application/json", "Stripe-Signature": "valid"},
    )
    assert r1.status_code == 200
    assert r1.get_json()["status"] == "processed"

    # Duplicate delivery
    r2 = client.post(
        "/api/v1/webhooks/stripe",
        data=json.dumps(webhook_payload),
        headers={"Content-Type": "application/json", "Stripe-Signature": "valid"},
    )
    assert r2.status_code == 200
    assert r2.get_json()["status"] == "ignored"
    assert r2.get_json()["reason"] == "duplicate_event"


def test_webhook_payment_failed_restores_stock(app, client):
    with app.app_context():
        init_prod = ProductModel.get_by_id(4)
        orig_stock = init_prod["stock_quantity"]

    token = _create_test_cart_with_item(client, product_id=4, quantity=2)
    res_order = client.post(
        "/api/v1/checkout/create-order",
        json={
            "cart_token": token,
            "customer_email": "failtest@shoppulse.dev",
            "customer_name": "Fail Test",
            "shipping_address": "888 Failure St",
        },
    )
    order = res_order.get_json()["data"]
    order_num = order["order_number"]
    intent_id = order["payment_intent_id"]

    # Stock was deducted during creation
    with app.app_context():
        assert ProductModel.get_by_id(4)["stock_quantity"] == orig_stock - 2

    # Webhook notifies payment failure
    fail_payload = {
        "id": "evt_test_failure_456",
        "type": "payment_intent.payment_failed",
        "data": {
            "object": {
                "id": intent_id,
                "metadata": {"order_number": order_num},
            }
        },
    }

    res_hook = client.post(
        "/api/v1/webhooks/stripe",
        data=json.dumps(fail_payload),
        headers={"Content-Type": "application/json", "Stripe-Signature": "valid"},
    )
    assert res_hook.status_code == 200

    # Verify status is cancelled and inventory is restored
    with app.app_context():
        updated_order = OrderModel.get_by_order_number(order_num)
        assert updated_order["status"] == "cancelled"
        assert ProductModel.get_by_id(4)["stock_quantity"] == orig_stock


def test_webhook_signature_failure(client):
    res = client.post(
        "/api/v1/webhooks/stripe",
        data=json.dumps({"id": "evt_bad_sig"}),
        headers={"Stripe-Signature": "invalid_sig"},
    )
    assert res.status_code == 400
    assert res.get_json()["code"] == "INVALID_SIGNATURE"


def test_simulate_payment_endpoint(client):
    token = _create_test_cart_with_item(client, product_id=5, quantity=1)
    res_order = client.post(
        "/api/v1/checkout/create-order",
        json={
            "cart_token": token,
            "customer_email": "sim@shoppulse.dev",
            "customer_name": "Sim User",
            "shipping_address": "555 Sim Ln",
        },
    )
    intent_id = res_order.get_json()["data"]["payment_intent_id"]

    # Simulate success
    res_sim = client.post(
        "/api/v1/checkout/simulate-payment",
        json={"payment_intent_id": intent_id, "scenario": "success"},
    )
    assert res_sim.status_code == 200
    assert res_sim.get_json()["order"]["status"] == "paid"

    # Simulate missing intent id
    res_missing = client.post("/api/v1/checkout/simulate-payment", json={})
    assert res_missing.status_code == 400

    # Simulate nonexistent intent id
    res_bad = client.post(
        "/api/v1/checkout/simulate-payment",
        json={"payment_intent_id": "pi_nonexistent"},
    )
    assert res_bad.status_code == 404


def test_order_model_invalid_transition(app, test_db_path):
    with app.app_context():
        # Illegal transition
        success, msg, _ = OrderModel.transition_status("NONEXISTENT", "paid")
        assert success is False

        token = CartModel.get_or_create()["token"]
        CartModel.add_item(token, 1, 1)
        _, _, order = OrderModel.create_order(
            token,
            "t@t.com",
            "N",
            "A",
        )
        ord_num = order["order_number"]

        # Valid: pending -> paid
        s1, _, _ = OrderModel.transition_status(ord_num, "paid")
        assert s1 is True

        # Invalid: paid -> pending
        s2, _, _ = OrderModel.transition_status(ord_num, "pending")
        assert s2 is False


def test_payment_adapter_direct():
    adapter = get_payment_adapter()

    with pytest.raises(PaymentError):
        adapter.create_payment_intent(-100)

    with pytest.raises(SignatureVerificationError):
        adapter.verify_webhook_signature("invalid json {", "sig", "secret")

    with pytest.raises(SignatureVerificationError):
        adapter.verify_webhook_signature(b"valid", "", "secret")
