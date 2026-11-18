"""Unit and integration tests for Order Service, Saga Coordinator, and Rollbacks."""

import sqlite3
from unittest.mock import MagicMock

import pytest

from services.order.app import create_order_app
from services.order.models import OrderModel
from services.order.saga import OrderSagaCoordinator
from shared.client import PulseClient, PulseResponse
from shared.message_broker import MessageBroker


@pytest.fixture
def order_db() -> sqlite3.Connection:
    """Fixture providing an in-memory SQLite database for Order Service."""
    conn = OrderModel.get_connection(":memory:")
    OrderModel.init_db(conn)
    return conn


@pytest.fixture
def broker() -> MessageBroker:
    """Fixture providing an isolated MessageBroker."""
    return MessageBroker()


def test_order_model_crud(order_db: sqlite3.Connection):
    """Test OrderModel CRUD operations and validation checks."""
    items = [
        {"product_id": "prod_1", "quantity": 2, "price_cents": 1000},
        {"product_id": "prod_2", "quantity": 1, "price_cents": 500},
    ]
    order = OrderModel.create_order(
        conn=order_db,
        user_id="usr_test_1",
        total_cents=2500,
        items=items,
        correlation_id="corr_test_1",
    )
    assert order["id"].startswith("ord_")
    assert order["user_id"] == "usr_test_1"
    assert order["total_cents"] == 2500
    assert order["status"] == "PENDING"
    assert len(order["items"]) == 2

    # Get single order
    fetched = OrderModel.get_order(order_db, order["id"])
    assert fetched is not None
    assert fetched["id"] == order["id"]

    # Update status
    updated = OrderModel.update_order_status(order_db, order["id"], "COMPLETED")
    assert updated is True
    refetched = OrderModel.get_order(order_db, order["id"])
    assert refetched["status"] == "COMPLETED"

    # List orders
    all_orders = OrderModel.list_orders(order_db)
    assert len(all_orders) == 1
    user_orders = OrderModel.list_orders(order_db, user_id="usr_test_1")
    assert len(user_orders) == 1


def test_order_model_validation_errors(order_db: sqlite3.Connection):
    """Test OrderModel input validation rejections."""
    with pytest.raises(ValueError, match="User ID cannot be empty"):
        OrderModel.create_order(order_db, "", 100, [{"sku": "x"}], "c1")

    with pytest.raises(ValueError, match="Total cents cannot be negative"):
        OrderModel.create_order(order_db, "u1", -5, [{"sku": "x"}], "c1")

    with pytest.raises(ValueError, match="Order items cannot be empty"):
        OrderModel.create_order(order_db, "u1", 100, [], "c1")


def test_saga_trace_recording(order_db: sqlite3.Connection):
    """Test recording and retrieving distributed saga execution steps."""
    order = OrderModel.create_order(
        conn=order_db,
        user_id="usr_trace",
        total_cents=1000,
        items=[{"sku": "SKU-1", "quantity": 1}],
        correlation_id="corr_trace",
    )
    oid = order["id"]

    OrderModel.record_saga_step(
        order_db, oid, "VERIFY_USER", "COMPLETED", {"user_id": "usr_trace"}
    )
    OrderModel.record_saga_step(
        order_db, oid, "RESERVE_STOCK", "COMPLETED", {"units": 1}
    )

    trace = OrderModel.get_saga_trace(order_db, oid)
    assert len(trace) == 2
    assert trace[0]["step_name"] == "VERIFY_USER"
    assert trace[0]["status"] == "COMPLETED"
    assert trace[1]["step_name"] == "RESERVE_STOCK"


def test_saga_happy_path(order_db: sqlite3.Connection, broker: MessageBroker):
    """Test full successful distributed checkout saga."""
    events_received = []
    broker.subscribe("orders.events", "auditor", lambda e: events_received.append(e))

    stock_reserved = False
    stock_committed = False

    def mock_reserver(oid, items, corr):
        nonlocal stock_reserved
        stock_reserved = True
        return True, ""

    def mock_committer(oid, corr):
        nonlocal stock_committed
        stock_committed = True
        return True, ""

    coordinator = OrderSagaCoordinator(
        conn=order_db,
        broker=broker,
        stock_reserver=mock_reserver,
        stock_committer=mock_committer,
    )

    items = [{"product_id": "p1", "quantity": 2, "price_cents": 500}]
    result = coordinator.execute_saga(
        user_id="usr_alice",
        total_cents=1000,
        items=items,
    )

    assert result["success"] is True
    assert result["order"]["status"] == "COMPLETED"
    assert stock_reserved is True
    assert stock_committed is True

    # Verify event published
    assert len(events_received) == 1
    assert events_received[0].type == "order.completed"
    assert events_received[0].data["user_id"] == "usr_alice"


def test_saga_user_verification_failure(
    order_db: sqlite3.Connection, broker: MessageBroker
):
    """Test saga terminates immediately when user verification fails."""
    coordinator = OrderSagaCoordinator(
        conn=order_db,
        broker=broker,
        user_verifier=lambda uid, corr: (False, "User account suspended"),
    )

    result = coordinator.execute_saga(
        user_id="usr_banned",
        total_cents=5000,
        items=[{"product_id": "p1", "quantity": 1}],
    )

    assert result["success"] is False
    assert result["status"] == "FAILED"
    assert result["failed_step"] == "VERIFY_USER"
    assert "suspended" in result["error"]

    # Verify order state in db
    order = OrderModel.get_order(order_db, result["order_id"])
    assert order["status"] == "FAILED"


def test_saga_stock_reservation_failure(
    order_db: sqlite3.Connection, broker: MessageBroker
):
    """Test saga halts when inventory cannot be reserved."""
    coordinator = OrderSagaCoordinator(
        conn=order_db,
        broker=broker,
        stock_reserver=lambda oid, items, corr: (
            False,
            "Insufficient stock for product p1",
        ),
    )

    result = coordinator.execute_saga(
        user_id="usr_bob",
        total_cents=5000,
        items=[{"product_id": "p1", "quantity": 100}],
    )

    assert result["success"] is False
    assert result["status"] == "FAILED"
    assert result["failed_step"] == "RESERVE_STOCK"
    assert "Insufficient stock" in result["error"]


def test_saga_payment_failure_with_compensating_rollback(
    order_db: sqlite3.Connection, broker: MessageBroker
):
    """Test simulated payment failure triggers compensating stock release rollback."""
    events_received = []
    broker.subscribe("orders.events", "audit", lambda e: events_received.append(e))

    stock_released = False

    def mock_releaser(oid, corr):
        nonlocal stock_released
        stock_released = True
        return True, ""

    coordinator = OrderSagaCoordinator(
        conn=order_db,
        broker=broker,
        stock_releaser=mock_releaser,
    )

    items = [{"product_id": "p1", "quantity": 1, "price_cents": 2000}]
    result = coordinator.execute_saga(
        user_id="usr_charlie",
        total_cents=2000,
        items=items,
        simulate_payment_failure=True,
    )

    assert result["success"] is False
    assert result["status"] == "CANCELLED"
    assert result["failed_step"] == "PROCESS_PAYMENT"
    assert result["compensated"] is True
    assert stock_released is True

    # Check order status in DB
    order = OrderModel.get_order(order_db, result["order_id"])
    assert order["status"] == "CANCELLED"

    # Check saga trace contains COMPENSATE_STOCK_RELEASE -> COMPENSATED
    trace = OrderModel.get_saga_trace(order_db, result["order_id"])
    comp_step = next(
        (
            s
            for s in trace
            if s["step_name"] == "COMPENSATE_STOCK_RELEASE"
            and s["status"] == "COMPENSATED"
        ),
        None,
    )
    assert comp_step is not None

    # Check event order.cancelled published
    assert len(events_received) == 1
    assert events_received[0].type == "order.cancelled"
    assert events_received[0].data["order_id"] == result["order_id"]


def test_saga_compensation_failure_handling(
    order_db: sqlite3.Connection, broker: MessageBroker
):
    """Test handling when compensating stock release itself encounters failure."""
    coordinator = OrderSagaCoordinator(
        conn=order_db,
        broker=broker,
        stock_releaser=lambda oid, corr: (False, "Network timeout during release"),
    )

    result = coordinator.execute_saga(
        user_id="usr_dave",
        total_cents=1000,
        items=[{"product_id": "p1", "quantity": 1}],
        simulate_payment_failure=True,
    )

    assert result["success"] is False
    assert result["status"] == "CANCELLED"
    assert result["compensated"] is False

    trace = OrderModel.get_saga_trace(order_db, result["order_id"])
    comp_failed = next((s for s in trace if s["status"] == "COMPENSATION_FAILED"), None)
    assert comp_failed is not None


def test_saga_commit_failure_handling(
    order_db: sqlite3.Connection, broker: MessageBroker
):
    """Test handling when stock commit step encounters failure."""
    coordinator = OrderSagaCoordinator(
        conn=order_db,
        broker=broker,
        stock_committer=lambda oid, corr: (False, "Database lock on commit"),
    )

    result = coordinator.execute_saga(
        user_id="usr_eve",
        total_cents=1000,
        items=[{"product_id": "p1", "quantity": 1}],
    )

    assert result["success"] is False
    assert result["status"] == "FAILED"
    assert result["failed_step"] == "COMMIT_STOCK"


def test_saga_with_pulse_client_http_mocks(
    order_db: sqlite3.Connection, broker: MessageBroker
):
    """Test saga coordinator utilizing PulseClient with mock HTTP responses."""
    mock_client = MagicMock(spec=PulseClient)

    # 1. User verification returns healthy user
    mock_client.get.return_value = PulseResponse(
        status_code=200,
        headers={},
        data={"user": {"id": "usr_pulse", "is_active": True}},
        raw_text="",
        latency_ms=10.0,
        instance_id="user-01",
        service_name="user-service",
    )

    # 2. Inventory reserve and commit return 200
    mock_client.post.return_value = PulseResponse(
        status_code=200,
        headers={},
        data={"status": "RESERVED"},
        raw_text="",
        latency_ms=15.0,
        instance_id="catalog-01",
        service_name="catalog-service",
    )

    coordinator = OrderSagaCoordinator(
        conn=order_db,
        pulse_client=mock_client,
        broker=broker,
    )

    result = coordinator.execute_saga(
        user_id="usr_pulse",
        total_cents=1500,
        items=[{"product_id": "prod_1", "quantity": 1}],
    )

    assert result["success"] is True
    assert mock_client.get.call_count == 1
    assert mock_client.post.call_count == 2  # reserve + commit


def test_order_service_rest_api():
    """Test Order Service REST endpoints via Flask test client."""
    app = create_order_app(db_path=":memory:")
    client = app.test_client()

    # 1. Health probe
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json["service"] == "order-service"

    # 2. Validation error - missing user_id
    res = client.post("/api/v1/orders", json={"items": [{"sku": "x"}]})
    assert res.status_code == 400

    # 3. Validation error - empty items
    res = client.post("/api/v1/orders", json={"user_id": "u1", "items": []})
    assert res.status_code == 400

    # 4. Successful order creation (default mocked hooks)
    res = client.post(
        "/api/v1/orders",
        json={
            "user_id": "usr_api",
            "items": [{"product_id": "p1", "quantity": 2, "price_cents": 500}],
            "total_cents": 1000,
        },
    )
    assert res.status_code == 201
    data = res.json
    assert data["success"] is True
    oid = data["order"]["id"]

    # 5. Get order by ID
    res = client.get(f"/api/v1/orders/{oid}")
    assert res.status_code == 200
    assert res.json["order"]["id"] == oid

    # 6. Get non-existent order
    res = client.get("/api/v1/orders/ord_nonexistent")
    assert res.status_code == 404

    # 7. Get saga trace
    res = client.get(f"/api/v1/orders/{oid}/saga-trace")
    assert res.status_code == 200
    assert len(res.json["trace"]) > 0

    # 8. List orders
    res = client.get("/api/v1/orders?user_id=usr_api")
    assert res.status_code == 200
    assert res.json["count"] == 1

    # 9. Payment failure returns 402 with CANCELLED status
    res = client.post(
        "/api/v1/orders",
        json={
            "user_id": "usr_fail",
            "items": [{"product_id": "p1", "quantity": 1, "price_cents": 500}],
            "simulate_payment_failure": True,
        },
    )
    assert res.status_code == 402
    assert res.json["status"] == "CANCELLED"

    # 10. Trace for non-existent order returns 404
    res = client.get("/api/v1/orders/ord_missing/saga-trace")
    assert res.status_code == 404

    # 11. User verification failure returns 422
    fail_conn = OrderModel.get_connection(":memory:")
    OrderModel.init_db(fail_conn)
    app_fail = create_order_app(
        coordinator=OrderSagaCoordinator(
            conn=fail_conn,
            user_verifier=lambda u, c: (False, "Inactive user"),
        ),
    )
    res_fail = app_fail.test_client().post(
        "/api/v1/orders",
        json={
            "user_id": "usr_inactive",
            "items": [{"product_id": "p1", "quantity": 1}],
        },
    )
    assert res_fail.status_code == 422

    # 12. Negative total cents returns 400
    res_neg = client.post(
        "/api/v1/orders",
        json={
            "user_id": "u1",
            "items": [{"product_id": "p1", "quantity": 1}],
            "total_cents": -100,
        },
    )
    assert res_neg.status_code == 400

    # 13. List orders without query params
    res_all = client.get("/api/v1/orders")
    assert res_all.status_code == 200


def test_saga_pulse_client_error_branches(
    order_db: sqlite3.Connection, broker: MessageBroker
):
    """Test PulseClient error branches across user, catalog reserve, and release."""
    mock_client = MagicMock(spec=PulseClient)

    # 1. User service returns 404
    mock_client.get.return_value = PulseResponse(
        status_code=404,
        headers={},
        data={"error": "Not found"},
        raw_text="Not found",
        latency_ms=10.0,
        instance_id="user-01",
        service_name="user-service",
    )
    coord = OrderSagaCoordinator(conn=order_db, pulse_client=mock_client, broker=broker)
    res = coord.execute_saga(
        user_id="usr_404",
        total_cents=1000,
        items=[{"product_id": "p1", "quantity": 1}],
    )
    assert res["status"] == "FAILED"
    assert res["failed_step"] == "VERIFY_USER"

    # 2. User service returns inactive user
    mock_client.get.return_value = PulseResponse(
        status_code=200,
        headers={},
        data={"user": {"id": "usr_suspended", "is_active": False}},
        raw_text="",
        latency_ms=10.0,
        instance_id="user-01",
        service_name="user-service",
    )
    res = coord.execute_saga(
        user_id="usr_suspended",
        total_cents=1000,
        items=[{"product_id": "p1", "quantity": 1}],
    )
    assert res["status"] == "FAILED"
    assert "suspended" in res["error"]

    # 3. User service throws connection exception
    mock_client.get.side_effect = RuntimeError("Connection timeout")
    res = coord.execute_saga(
        user_id="usr_err",
        total_cents=1000,
        items=[{"product_id": "p1", "quantity": 1}],
    )
    assert res["status"] == "FAILED"
    assert "connection error" in res["error"].lower()
    mock_client.get.side_effect = None

    # 4. Catalog reserve returns 400
    mock_client.get.return_value = PulseResponse(
        status_code=200,
        headers={},
        data={"user": {"id": "usr_valid", "is_active": True}},
        raw_text="",
        latency_ms=5.0,
        instance_id="user-01",
        service_name="user-service",
    )
    mock_client.post.return_value = PulseResponse(
        status_code=400,
        headers={},
        data={"error": "Out of stock"},
        raw_text='{"error": "Out of stock"}',
        latency_ms=8.0,
        instance_id="catalog-01",
        service_name="catalog-service",
    )
    res = coord.execute_saga(
        user_id="usr_valid",
        total_cents=1000,
        items=[{"product_id": "p1", "quantity": 1}],
    )
    assert res["status"] == "FAILED"
    assert res["failed_step"] == "RESERVE_STOCK"

    # 5. Catalog reserve throws connection exception
    mock_client.post.side_effect = RuntimeError("Socket error")
    res = coord.execute_saga(
        user_id="usr_valid",
        total_cents=1000,
        items=[{"product_id": "p1", "quantity": 1}],
    )
    assert res["status"] == "FAILED"
    assert "Catalog service connection error" in res["error"]
    mock_client.post.side_effect = None

    # 6. Catalog release fails during compensation
    # Reserve succeeds, payment fails, release fails
    mock_client.post.side_effect = [
        # Reserve succeeds
        PulseResponse(
            status_code=200,
            headers={},
            data={"status": "RESERVED"},
            raw_text="",
            latency_ms=5.0,
            instance_id="c1",
            service_name="catalog-service",
        ),
        # Release fails
        PulseResponse(
            status_code=500,
            headers={},
            data="Server error",
            raw_text="Server error",
            latency_ms=5.0,
            instance_id="c1",
            service_name="catalog-service",
        ),
    ]
    res = coord.execute_saga(
        user_id="usr_valid",
        total_cents=1000,
        items=[{"product_id": "p1", "quantity": 1}],
        simulate_payment_failure=True,
    )
    assert res["status"] == "CANCELLED"
    assert res["compensated"] is False
    mock_client.post.side_effect = None

    # 7. Catalog commit fails
    mock_client.post.side_effect = [
        # Reserve succeeds
        PulseResponse(
            status_code=200,
            headers={},
            data={"status": "RESERVED"},
            raw_text="",
            latency_ms=5.0,
            instance_id="c1",
            service_name="catalog-service",
        ),
        # Commit fails
        PulseResponse(
            status_code=500,
            headers={},
            data="Commit failed",
            raw_text="Commit failed",
            latency_ms=5.0,
            instance_id="c1",
            service_name="catalog-service",
        ),
    ]
    res = coord.execute_saga(
        user_id="usr_valid",
        total_cents=1000,
        items=[{"product_id": "p1", "quantity": 1}],
    )
    assert res["status"] == "FAILED"
    assert res["failed_step"] == "COMMIT_STOCK"
