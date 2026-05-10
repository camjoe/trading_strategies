from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from common.coercion import row_expect_float, row_expect_int, row_expect_str, row_float
from common.time import utc_now_iso
from trading.domain.sleeve_accounting import SleeveFillTransition, apply_sleeve_fill_transition
from trading.repositories.sleeve_ledger import (
    fetch_sleeve_ledger_sum_by_type,
    insert_sleeve_ledger_entry,
)
from trading.repositories.sleeve_orders import (
    fetch_sleeve_fills_for_order,
    fetch_sleeve_order_by_id,
    insert_sleeve_fill,
)
from trading.repositories.sleeve_positions import (
    delete_sleeve_position,
    fetch_sleeve_position,
    upsert_sleeve_position,
)
from trading.repositories.sleeves import (
    fetch_strategy_sleeve_by_id,
    update_strategy_sleeve_balances,
)

# Ledger entry type for gross cash movement from a fill event.
LEDGER_ENTRY_CASH_MOVEMENT = "cash_movement"
# Ledger entry type for explicit broker fees or commissions.
LEDGER_ENTRY_FEE = "fee"
# Ledger entry type for realized PnL caused by sell fills.
LEDGER_ENTRY_REALIZED_PNL = "realized_pnl"
# Ledger reference tag for sleeve fill-derived events.
LEDGER_REFERENCE_TYPE_SLEEVE_FILL = "sleeve_fill"


@dataclass(frozen=True, slots=True)
class SleeveFillApplicationResult:
    applied: bool
    reason: str | None
    sleeve_order_id: int
    sleeve_id: int
    transition: SleeveFillTransition | None


def _is_duplicate_exec_id(
    conn: sqlite3.Connection,
    *,
    sleeve_order_id: int,
    exec_id: str,
) -> bool:
    prior_fills = fetch_sleeve_fills_for_order(conn, sleeve_order_id=sleeve_order_id)
    return any(row_expect_str(row, "exec_id") == exec_id for row in prior_fills if row["exec_id"] is not None)


def _build_ledger_reference_id(
    *,
    sleeve_order_id: int,
    exec_id: str | None,
    broker_fill_id: str | None,
    fill_time: str,
) -> str:
    if exec_id:
        return exec_id
    if broker_fill_id:
        return broker_fill_id
    return f"{sleeve_order_id}:{fill_time}"


def apply_sleeve_fill(
    conn: sqlite3.Connection,
    *,
    sleeve_order_id: int,
    broker_fill_id: str | None,
    exec_id: str | None,
    filled_qty: float,
    fill_price: float,
    commission: float,
    fill_time: str,
    updated_at: str | None = None,
) -> SleeveFillApplicationResult:
    order_row = fetch_sleeve_order_by_id(conn, sleeve_order_id=sleeve_order_id)
    if order_row is None:
        raise ValueError(f"Sleeve order not found for id={sleeve_order_id}.")

    fill_count_before = len(fetch_sleeve_fills_for_order(conn, sleeve_order_id=sleeve_order_id))
    if exec_id and _is_duplicate_exec_id(conn, sleeve_order_id=sleeve_order_id, exec_id=exec_id):
        return SleeveFillApplicationResult(
            applied=False,
            reason="duplicate_exec_id",
            sleeve_order_id=int(sleeve_order_id),
            sleeve_id=row_expect_int(order_row, "sleeve_id"),
            transition=None,
        )

    sleeve_id = row_expect_int(order_row, "sleeve_id")
    sleeve_row = fetch_strategy_sleeve_by_id(conn, sleeve_id=sleeve_id)
    if sleeve_row is None:
        raise ValueError(f"Strategy sleeve not found for id={sleeve_id}.")

    symbol = row_expect_str(order_row, "symbol")
    side = row_expect_str(order_row, "side")
    requested_price = row_float(order_row, "requested_price")
    current_cash = row_expect_float(sleeve_row, "current_cash")
    current_realized_pnl = fetch_sleeve_ledger_sum_by_type(
        conn,
        sleeve_id=sleeve_id,
        entry_type=LEDGER_ENTRY_REALIZED_PNL,
    )

    position_row = fetch_sleeve_position(conn, sleeve_id=sleeve_id, symbol=symbol)
    current_qty = row_float(position_row, "qty") if position_row is not None else 0.0
    current_avg_cost = row_float(position_row, "avg_cost") if position_row is not None else 0.0

    transition = apply_sleeve_fill_transition(
        side=side,
        symbol=symbol,
        qty=float(filled_qty),
        fill_price=float(fill_price),
        commission=float(commission),
        requested_price=requested_price,
        position_qty=float(current_qty or 0.0),
        position_avg_cost=float(current_avg_cost or 0.0),
        cash=current_cash,
        realized_pnl=current_realized_pnl,
    )

    insert_sleeve_fill(
        conn,
        sleeve_order_id=int(sleeve_order_id),
        sleeve_id=sleeve_id,
        broker_fill_id=broker_fill_id,
        exec_id=exec_id,
        symbol=transition.symbol,
        filled_qty=transition.qty,
        fill_price=transition.fill_price,
        commission=transition.commission,
        fill_time=fill_time,
    )
    fill_count_after = len(fetch_sleeve_fills_for_order(conn, sleeve_order_id=sleeve_order_id))
    if fill_count_after == fill_count_before:
        return SleeveFillApplicationResult(
            applied=False,
            reason="duplicate_fill_ignored",
            sleeve_order_id=int(sleeve_order_id),
            sleeve_id=sleeve_id,
            transition=None,
        )

    event_time = updated_at or utc_now_iso()
    ledger_reference_id = _build_ledger_reference_id(
        sleeve_order_id=sleeve_order_id,
        exec_id=exec_id,
        broker_fill_id=broker_fill_id,
        fill_time=fill_time,
    )

    insert_sleeve_ledger_entry(
        conn,
        sleeve_id=sleeve_id,
        entry_type=LEDGER_ENTRY_CASH_MOVEMENT,
        amount=transition.cash_delta,
        reference_type=LEDGER_REFERENCE_TYPE_SLEEVE_FILL,
        reference_id=ledger_reference_id,
        entry_time=fill_time,
        created_at=event_time,
    )
    if transition.commission > 0:
        insert_sleeve_ledger_entry(
            conn,
            sleeve_id=sleeve_id,
            entry_type=LEDGER_ENTRY_FEE,
            amount=-transition.commission,
            reference_type=LEDGER_REFERENCE_TYPE_SLEEVE_FILL,
            reference_id=ledger_reference_id,
            entry_time=fill_time,
            created_at=event_time,
        )
    if transition.realized_pnl_delta != 0:
        insert_sleeve_ledger_entry(
            conn,
            sleeve_id=sleeve_id,
            entry_type=LEDGER_ENTRY_REALIZED_PNL,
            amount=transition.realized_pnl_delta,
            reference_type=LEDGER_REFERENCE_TYPE_SLEEVE_FILL,
            reference_id=ledger_reference_id,
            entry_time=fill_time,
            created_at=event_time,
        )

    if transition.ending_qty > 0:
        upsert_sleeve_position(
            conn,
            sleeve_id=sleeve_id,
            symbol=transition.symbol,
            qty=transition.ending_qty,
            avg_cost=transition.ending_avg_cost,
            market_value=transition.ending_market_value,
            unrealized_pnl=transition.ending_unrealized_pnl,
            updated_at=event_time,
        )
    else:
        delete_sleeve_position(conn, sleeve_id=sleeve_id, symbol=transition.symbol)

    update_strategy_sleeve_balances(
        conn,
        sleeve_id=sleeve_id,
        current_cash=transition.ending_cash,
        current_equity=transition.ending_equity,
        updated_at=event_time,
    )
    return SleeveFillApplicationResult(
        applied=True,
        reason=None,
        sleeve_order_id=int(sleeve_order_id),
        sleeve_id=sleeve_id,
        transition=transition,
    )
