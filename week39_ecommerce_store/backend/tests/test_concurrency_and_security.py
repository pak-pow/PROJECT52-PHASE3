import concurrent.futures
import json
import threading

from app.db import get_db, query_db
from app.services.payment_service import get_payment_adapter


def test_concurrent_checkout_race_condition_prevents_overselling(app, client):
    """
    Simulates 10 concurrent shoppers racing to purchase the last item in stock.
    Database ACID transactions and atomic rowcount checks ensure that exactly 1
    shopper successfully creates an order (HTTP 201), while all other 9 receive
    HTTP 409 Conflict with INSUFFICIENT_STOCK. Stock must never fall below zero.
    """
    # 1. Isolate a test product with exactly 1 unit of stock
    with app.app_context():
        conn = get_db()
        conn.execute("UPDATE products SET stock_quantity = 1 WHERE id = 1")
        conn.commit()

        # Verify initial stock is exactly 1
        prod = query_db("SELECT stock_quantity FROM products WHERE id = 1", one=True)
        assert prod["stock_quantity"] == 1

    num_threads = 10
    cart_tokens = []

    # 2. Set up 10 independent carts, each with 1 quantity of product 1
    for i in range(num_threads):
        res = client.post(
            "/api/v1/cart/items",
            json={"product_id": 1, "quantity": 1},
        )
        assert res.status_code == 200
        token = res.headers.get("X-Cart-Token")
        assert token is not None
        cart_tokens.append(token)

    # 3. Synchronize concurrent execution with a threading barrier
    barrier = threading.Barrier(num_threads)
    results = []

    def attempt_checkout(token, index):
        barrier.wait()
        # Use an independent test client request context per thread
        with app.test_client() as thread_client:
            response = thread_client.post(
                "/api/v1/checkout/create-order",
                headers={"X-Cart-Token": token},
                json={
                    "customer_name": f"Shopper {index}",
                    "customer_email": f"shopper{index}@example.com",
                    "shipping_address": f"{index} Concurrency Lane, Austin, TX",
                },
            )
            return response.status_code, response.get_json()

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [
            executor.submit(attempt_checkout, cart_tokens[i], i)
            for i in range(num_threads)
        ]
        for f in concurrent.futures.as_completed(futures):
            results.append(f.result())

    successes = [r for r in results if r[0] == 201]
    conflicts = [r for r in results if r[0] == 409]

    # 4. Strict assertions: Exactly 1 winner, exactly 9 conflicts
    assert len(successes) == 1, f"Expected 1 successful order, got {len(successes)}"
    assert (
        len(conflicts) == num_threads - 1
    ), f"Expected {num_threads - 1} 409 conflicts"
    assert all(c[1]["code"] == "INSUFFICIENT_STOCK" for c in conflicts)

    # 5. Verify database stock is exactly 0 and never negative
    with app.app_context():
        final_prod = query_db(
            "SELECT stock_quantity FROM products WHERE id = 1", one=True
        )
        assert final_prod["stock_quantity"] == 0


def test_sql_injection_defense_on_catalog_queries(client):
    """
    Verifies that malicious SQL payloads in search, sort, and category parameters
    are safely parameterized and cannot alter query logic or execute arbitrary SQL.
    """
    # SQL injection attempts on search parameter
    injection_payloads = [
        "' OR '1'='1",
        "'; DROP TABLE products; --",
        (
            "' UNION SELECT id, sku, title, slug, description, price_cents, "
            "1, 1, 1, 1, 1 FROM products --"
        ),
        "1' OR 1=1 ORDER BY 1 --",
    ]

    for payload in injection_payloads:
        res = client.get(f"/api/v1/products?search={payload}")
        assert res.status_code == 200
        data = res.get_json()
        assert data["status"] == "success"
        assert isinstance(data["data"], list)

    # SQL injection on sort parameter
    res = client.get("/api/v1/products?sort=price_asc; DROP TABLE products; --")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"

    # SQL injection on category parameter
    res = client.get("/api/v1/products?category=' OR '1'='1")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    # Parameterized query treats this as a literal category name and returns 0 items
    assert len(data["data"]) == 0


def test_xss_injection_sanitization_in_orders(client):
    """
    Verifies that HTML and script injection attempts in customer details are
    properly sanitized and escaped in order storage and invoice generation.
    """
    # 1. Add item to cart
    res = client.post("/api/v1/cart/items", json={"product_id": 2, "quantity": 1})
    assert res.status_code == 200
    token = res.headers["X-Cart-Token"]

    # 2. Checkout with script tags
    xss_name = "<script>alert('pwned')</script>"
    xss_address = "<img src=x onerror=alert('xss')> 100 Hack Way"

    checkout_res = client.post(
        "/api/v1/checkout/create-order",
        headers={"X-Cart-Token": token},
        json={
            "customer_name": xss_name,
            "customer_email": "security@example.com",
            "shipping_address": xss_address,
        },
    )
    assert checkout_res.status_code == 201
    order = checkout_res.get_json()["data"]
    order_num = order["order_number"]

    # Check that raw tags were converted to HTML entities
    assert "<script>" not in order["customer_name"]
    assert "&lt;script&gt;" in order["customer_name"]
    assert "<img" not in order["shipping_address"]
    assert "&lt;img" in order["shipping_address"]

    # 3. Verify retrieval via GET /api/v1/orders/<order_number>
    get_res = client.get(f"/api/v1/orders/{order_num}")
    assert get_res.status_code == 200
    fetched_order = get_res.get_json()["data"]
    assert "&lt;script&gt;" in fetched_order["customer_name"]

    # 4. Verify invoice endpoint
    inv_res = client.get(f"/api/v1/orders/{order_num}/invoice")
    assert inv_res.status_code == 200
    invoice = inv_res.get_json()["data"]
    assert "&lt;script&gt;" in invoice["customer"]["name"]
    assert "&lt;img" in invoice["customer"]["shipping_address"]


def test_promo_code_validation_and_fuzzing(client):
    """
    Verifies that malformed, oversized, or malicious promo codes are strictly rejected.
    """
    # Empty or whitespace promo
    res = client.post("/api/v1/cart/promo", json={"promo_code": ""})
    assert res.status_code == 400
    assert res.get_json()["code"] == "INVALID_PROMO_CODE"

    res = client.post("/api/v1/cart/promo", json={"promo_code": "   "})
    assert res.status_code == 400
    assert res.get_json()["code"] == "INVALID_PROMO_CODE"

    # Oversized buffer overflow attempt (> 30 chars)
    oversized_code = "A" * 500
    res = client.post("/api/v1/cart/promo", json={"promo_code": oversized_code})
    assert res.status_code == 400
    assert res.get_json()["code"] == "INVALID_PROMO_CODE"

    # Non-string payload
    res = client.post("/api/v1/cart/promo", json={"promo_code": 12345})
    assert res.status_code == 400
    assert res.get_json()["code"] == "INVALID_PROMO_CODE"


def test_webhook_cryptographic_forgery_rejection(client):
    """
    Verifies that forged, tampered, or missing webhook signatures are rejected with 400.
    """
    # 1. Missing signature header
    res = client.post(
        "/api/v1/webhooks/stripe",
        data='{"id": "evt_fake"}',
        headers={"Content-Type": "application/json"},
    )
    assert res.status_code == 400
    assert res.get_json()["code"] == "INVALID_SIGNATURE"

    # 2. Forged signature header
    res = client.post(
        "/api/v1/webhooks/stripe",
        data='{"id": "evt_fake"}',
        headers={
            "Content-Type": "application/json",
            "Stripe-Signature": "invalid_sig",
        },
    )
    assert res.status_code == 400
    assert res.get_json()["code"] == "INVALID_SIGNATURE"


def test_webhook_idempotency_prevents_duplicate_processing(client):
    """
    Verifies that replayed webhook deliveries are recognized by the idempotency ledger
    and do not duplicate order state transitions or processing actions.
    """
    # 1. Create order
    cart_res = client.post("/api/v1/cart/items", json={"product_id": 3, "quantity": 1})
    token = cart_res.headers["X-Cart-Token"]

    order_res = client.post(
        "/api/v1/checkout/create-order",
        headers={"X-Cart-Token": token},
        json={
            "customer_name": "Idempotency Test",
            "customer_email": "idempotency@example.com",
            "shipping_address": "1 Ledger Rd",
        },
    )
    order = order_res.get_json()["data"]
    order_num = order["order_number"]
    intent_id = order["payment_intent_id"]

    # 2. Generate valid mock webhook event
    adapter = get_payment_adapter()
    sim_event = adapter.simulate_payment(
        payment_intent_id=intent_id,
        scenario="success",
        metadata={"order_number": order_num},
    )
    payload_str = json.dumps(sim_event)

    # 3. First webhook delivery
    delivery_1 = client.post(
        "/api/v1/webhooks/stripe",
        data=payload_str,
        headers={
            "Content-Type": "application/json",
            "Stripe-Signature": "valid_sig",
        },
    )
    assert delivery_1.status_code == 200
    assert delivery_1.get_json()["status"] == "processed"

    # Check order is paid
    check_1 = client.get(f"/api/v1/orders/{order_num}")
    assert check_1.get_json()["data"]["status"] == "paid"

    # 4. Duplicate (replayed) webhook delivery with exact same event ID
    delivery_2 = client.post(
        "/api/v1/webhooks/stripe",
        data=payload_str,
        headers={
            "Content-Type": "application/json",
            "Stripe-Signature": "valid_sig",
        },
    )
    assert delivery_2.status_code == 200
    data_2 = delivery_2.get_json()
    assert data_2["status"] == "ignored"
    assert data_2.get("reason") == "duplicate_event"
