"""Broker order reconciliation helpers for runtime auto-trading."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from typing import Any

from common.coercion import row_expect_int
from common.time import utc_now_iso
from trading.models import AccountRecord
from trading.models.broker_order import OrderFill, OrderStatus
from trading.services.sleeves.accounting import apply_sleeve_fill


def resolve_reconciliation_exec_id(
    *,
    broker_order_id: str,
    fill: OrderFill,
    fill_index: int,
) -> str:
    if fill.exec_id:
        return fill.exec_id
    return f"{broker_order_id}:{fill.fill_time}:{fill.filled_qty}:{fill.fill_price}:{fill_index}"


def reconcile_open_broker_orders_impl(
    conn: sqlite3.Connection,
    account_name: str,
    account: AccountRecord,
    fee: float,
    *,
    get_broker_for_account_fn: Callable[..., Any],
    fetch_open_broker_orders_fn: Callable[..., list[Any]],
    fetch_sleeve_order_by_broker_order_id_fn: Callable[..., Any],
    insert_order_fill_fn: Callable[..., object],
    update_broker_order_status_fn: Callable[..., object],
    update_sleeve_order_status_fn: Callable[..., object],
    record_trade_fn: Callable[..., object],
) -> int:
    broker = get_broker_for_account_fn(account)

    open_rows = fetch_open_broker_orders_fn(account_id=row_expect_int(account, "id"))
    if not open_rows:
        broker.disconnect()
        return 0

    open_ids = {row.broker_order_id: row for row in open_rows}
    account_id = row_expect_int(account, "id")
    try:
        live_orders = broker.get_open_trades()
        now = utc_now_iso()
        newly_filled = 0

        for live in live_orders:
            if live.broker_order_id not in open_ids:
                continue
            persisted = open_ids[live.broker_order_id]
            sleeve_order_row = fetch_sleeve_order_by_broker_order_id_fn(
                conn,
                account_id=account_id,
                broker_order_id=live.broker_order_id,
            )

            for fill_index, fill in enumerate(live.fills):
                insert_order_fill_fn(live.broker_order_id, fill)
                if sleeve_order_row is not None:
                    apply_sleeve_fill(
                        conn,
                        sleeve_order_id=int(sleeve_order_row["id"]),
                        broker_fill_id=live.broker_order_id,
                        exec_id=resolve_reconciliation_exec_id(
                            broker_order_id=live.broker_order_id,
                            fill=fill,
                            fill_index=fill_index,
                        ),
                        filled_qty=fill.filled_qty,
                        fill_price=fill.fill_price,
                        commission=fill.commission,
                        fill_time=fill.fill_time,
                        updated_at=now,
                    )

            update_broker_order_status_fn(
                broker_order_id=live.broker_order_id,
                status=live.status,
                filled_qty=live.filled_qty,
                avg_fill_price=live.avg_fill_price,
                commission=live.commission,
                updated_at=now,
            )
            if sleeve_order_row is not None:
                update_sleeve_order_status_fn(
                    conn,
                    sleeve_order_id=int(sleeve_order_row["id"]),
                    status=live.status.value,
                    updated_at=now,
                )

            if live.status == OrderStatus.FILLED:
                record_trade_fn(
                    conn,
                    account_name=account_name,
                    side=persisted.side,
                    ticker=persisted.ticker,
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
