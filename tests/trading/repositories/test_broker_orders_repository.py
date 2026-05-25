from __future__ import annotations

from trading.models.broker_order import BrokerOrder, OrderFill, OrderStatus, OrderType, TimeInForce
from trading.repositories.broker_orders import (
    fetch_broker_orders_for_account,
    fetch_open_broker_orders,
    insert_broker_order,
    insert_order_fill,
    update_broker_order_status,
)
from tests.support.repositories import insert_repository_account


def _make_order(
    *,
    account_id: int,
    broker_order_id: str,
    submitted_at: str,
    status: OrderStatus,
    qty: float = 10.0,
) -> BrokerOrder:
    return BrokerOrder(
        account_id=account_id,
        broker_order_id=broker_order_id,
        ticker="SPY",
        side="buy",
        qty=qty,
        price=500.0,
        order_type=OrderType.LIMIT,
        time_in_force=TimeInForce.DAY,
        status=status,
        filled_qty=0.0,
        avg_fill_price=None,
        commission=0.0,
        submitted_at=submitted_at,
        updated_at=submitted_at,
    )


def test_insert_update_and_fetch_broker_orders(conn) -> None:
    account_id = insert_repository_account(conn, name="broker_orders_acct")
    other_account_id = insert_repository_account(conn, name="broker_orders_other")

    insert_broker_order(
        conn,
        _make_order(
            account_id=account_id,
            broker_order_id="bo-1",
            submitted_at="2026-05-03T10:00:00Z",
            status=OrderStatus.SUBMITTED,
        ),
    )
    insert_broker_order(
        conn,
        _make_order(
            account_id=account_id,
            broker_order_id="bo-2",
            submitted_at="2026-05-03T10:01:00Z",
            status=OrderStatus.ACCEPTED,
        ),
    )
    insert_broker_order(
        conn,
        _make_order(
            account_id=account_id,
            broker_order_id="bo-3",
            submitted_at="2026-05-03T10:02:00Z",
            status=OrderStatus.FILLED,
        ),
    )
    insert_broker_order(
        conn,
        _make_order(
            account_id=account_id,
            broker_order_id="bo-4",
            submitted_at="2026-05-03T10:03:00Z",
            status=OrderStatus.REJECTED,
        ),
    )
    insert_broker_order(
        conn,
        _make_order(
            account_id=other_account_id,
            broker_order_id="bo-other",
            submitted_at="2026-05-03T10:04:00Z",
            status=OrderStatus.SUBMITTED,
        ),
    )

    update_broker_order_status(
        conn,
        broker_order_id="bo-1",
        status=OrderStatus.PARTIALLY_FILLED,
        filled_qty=4.0,
        avg_fill_price=501.25,
        commission=1.5,
        updated_at="2026-05-03T10:05:00Z",
    )

    all_rows = fetch_broker_orders_for_account(conn, account_id=account_id)
    assert [row["broker_order_id"] for row in all_rows] == ["bo-1", "bo-2", "bo-3", "bo-4"]
    assert all_rows[0]["status"] == OrderStatus.PARTIALLY_FILLED.value
    assert float(all_rows[0]["filled_qty"]) == 4.0
    assert float(all_rows[0]["avg_fill_price"]) == 501.25
    assert float(all_rows[0]["commission"]) == 1.5

    open_rows = fetch_open_broker_orders(conn, account_id=account_id)
    assert [row["broker_order_id"] for row in open_rows] == ["bo-1", "bo-2"]


def test_insert_order_fill_is_idempotent_only_for_non_null_exec_ids(conn) -> None:
    account_id = insert_repository_account(conn, name="broker_fill_acct")
    insert_broker_order(
        conn,
        _make_order(
            account_id=account_id,
            broker_order_id="bo-fill",
            submitted_at="2026-05-03T11:00:00Z",
            status=OrderStatus.SUBMITTED,
        ),
    )

    fill = OrderFill(
        filled_qty=5.0,
        fill_price=499.5,
        fill_time="2026-05-03T11:01:00Z",
        commission=0.5,
        exec_id="exec-1",
    )
    insert_order_fill(conn, "bo-fill", fill)
    insert_order_fill(conn, "bo-fill", fill)

    paper_fill = OrderFill(
        filled_qty=1.0,
        fill_price=500.0,
        fill_time="2026-05-03T11:02:00Z",
        commission=0.0,
        exec_id=None,
    )
    insert_order_fill(conn, "bo-fill", paper_fill)
    insert_order_fill(conn, "bo-fill", paper_fill)

    rows = conn.execute(
        "SELECT exec_id, filled_qty, fill_price FROM order_fills WHERE broker_order_id = ? ORDER BY id ASC",
        ("bo-fill",),
    ).fetchall()

    assert [row["exec_id"] for row in rows] == ["exec-1", None, None]
    assert float(rows[0]["filled_qty"]) == 5.0
    assert float(rows[0]["fill_price"]) == 499.5
