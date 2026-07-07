"""Open-order reconciliation for runtime auto-trading (clean book schema).

Polls the broker for fills on the account's open clean ``orders`` and applies any
new executions to the book (``order_fills`` + position/ledger/balances via the
shared ``apply_book_fill``), then mirrors the fill into the legacy account ledger
(``trades``) so account-level reporting stays in sync during the cutover window.
Paper brokers fill synchronously and report no open trades, so this is a no-op for
them; it matters for async live brokers.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from typing import Any

from common.coercion import row_expect_int
from common.time import utc_now_iso
from trading.models import AccountRecord
from trading.models.orders.broker_order import OrderFill, OrderStatus
from trading.repositories.orders import OrderRepository
from trading.services.execution.submission import apply_book_fill, clean_order_status


def resolve_reconciliation_exec_id(
    *,
    broker_order_id: str,
    fill: OrderFill,
    fill_index: int,
) -> str:
    if fill.exec_id:
        return fill.exec_id
    return f"{broker_order_id}:{fill.fill_time}:{fill.filled_qty}:{fill.fill_price}:{fill_index}"


def reconcile_open_orders_impl(
    conn: sqlite3.Connection,
    account_name: str,
    account: AccountRecord,
    fee: float,
    *,
    get_broker_for_account_fn: Callable[..., Any],
    record_trade_fn: Callable[..., object],
) -> int:
    broker = get_broker_for_account_fn(account)
    account_id = row_expect_int(account, "id")
    order_repo = OrderRepository(conn)

    open_orders = order_repo.fetch_open_for_account(account_id=account_id)
    open_by_broker_id = {order.broker_order_id: order for order in open_orders if order.broker_order_id}
    if not open_by_broker_id:
        broker.disconnect()
        return 0

    try:
        live_orders = broker.get_open_trades()
        now = utc_now_iso()
        newly_filled = 0

        for live in live_orders:
            persisted = open_by_broker_id.get(live.broker_order_id)
            if persisted is None:
                continue

            # Apply only executions we have not already recorded (exec_id dedup), so a
            # repeated poll of the same partial fill does not double-post to the book.
            seen_exec_ids = order_repo.fetch_fill_exec_ids(order_id=persisted.id)
            for fill_index, fill in enumerate(live.fills):
                exec_id = resolve_reconciliation_exec_id(
                    broker_order_id=live.broker_order_id,
                    fill=fill,
                    fill_index=fill_index,
                )
                if exec_id in seen_exec_ids:
                    continue
                order_repo.insert_fill(
                    order_id=persisted.id,
                    filled_qty=fill.filled_qty,
                    fill_price=fill.fill_price,
                    fill_time=fill.fill_time,
                    commission=fill.commission,
                    broker_fill_id=live.broker_order_id,
                    exec_id=exec_id,
                )
                apply_book_fill(
                    conn,
                    book_id=persisted.book_id,
                    order_id=persisted.id,
                    side=persisted.side,
                    symbol=persisted.symbol,
                    fill_qty=fill.filled_qty,
                    fill_price=fill.fill_price,
                    transaction_cost=fill.commission,
                    fill_time=fill.fill_time,
                )
                seen_exec_ids.add(exec_id)

            order_repo.update_status(
                order_id=persisted.id,
                status=clean_order_status(live.status),
                filled_qty=live.filled_qty,
                avg_fill_price=live.avg_fill_price,
                updated_at=now,
            )

            if live.status == OrderStatus.FILLED:
                record_trade_fn(
                    conn,
                    account_name=account_name,
                    side=persisted.side,
                    ticker=persisted.symbol,
                    qty=live.filled_qty,
                    price=live.avg_fill_price if live.avg_fill_price is not None else persisted.requested_price,
                    fee=fee,
                    trade_time=now,
                    note=f"ib-fill order={live.broker_order_id}",
                )
                newly_filled += 1

        return newly_filled
    finally:
        broker.disconnect()
