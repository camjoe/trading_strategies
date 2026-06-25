from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from common.time import utc_now_iso
from trading.domain.sleeve_accounting import apply_sleeve_fill_transition
from trading.models.sleeves.sleeve_fill_transition import SleeveFillTransition
from trading.repositories.sleeve_ledger import SleeveLedgerRepository
from trading.repositories.sleeve_orders import SleeveOrderRepository
from trading.repositories.sleeve_positions import SleevePositionRepository
from trading.repositories.sleeves import SleeveRepository

LEDGER_ENTRY_CASH_MOVEMENT = "cash_movement"
LEDGER_ENTRY_FEE = "fee"
LEDGER_ENTRY_REALIZED_PNL = "realized_pnl"
LEDGER_REFERENCE_TYPE_SLEEVE_FILL = "sleeve_fill"


@dataclass(frozen=True, slots=True)
class SleeveFillApplicationResult:
    applied: bool
    reason: str | None
    sleeve_order_id: int
    sleeve_id: int
    transition: SleeveFillTransition | None


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
    order_repo = SleeveOrderRepository(conn)
    sleeve_repo = SleeveRepository(conn)
    position_repo = SleevePositionRepository(conn)
    ledger_repo = SleeveLedgerRepository(conn)

    order = order_repo.fetch_by_id(sleeve_order_id=sleeve_order_id)
    if order is None:
        raise ValueError(f"Sleeve order not found for id={sleeve_order_id}.")

    prior_fills = order_repo.fetch_fills_for_order(sleeve_order_id=sleeve_order_id)
    if exec_id and any(f.exec_id == exec_id for f in prior_fills if f.exec_id is not None):
        return SleeveFillApplicationResult(
            applied=False,
            reason="duplicate_exec_id",
            sleeve_order_id=int(sleeve_order_id),
            sleeve_id=order.sleeve_id,
            transition=None,
        )

    sleeve = sleeve_repo.fetch_by_id(sleeve_id=order.sleeve_id)
    if sleeve is None:
        raise ValueError(f"Strategy sleeve not found for id={order.sleeve_id}.")

    current_realized_pnl = ledger_repo.fetch_sum_by_type(
        sleeve_id=order.sleeve_id,
        entry_type=LEDGER_ENTRY_REALIZED_PNL,
    )

    position = position_repo.fetch(sleeve_id=order.sleeve_id, symbol=order.symbol)
    current_qty = position.qty if position is not None else 0.0
    current_avg_cost = position.avg_cost if position is not None else 0.0

    transition = apply_sleeve_fill_transition(
        side=order.side,
        symbol=order.symbol,
        qty=float(filled_qty),
        fill_price=float(fill_price),
        commission=float(commission),
        requested_price=order.requested_price,
        position_qty=float(current_qty),
        position_avg_cost=float(current_avg_cost),
        cash=sleeve.current_cash,
        realized_pnl=current_realized_pnl,
    )

    order_repo.insert_fill(
        sleeve_order_id=int(sleeve_order_id),
        sleeve_id=order.sleeve_id,
        broker_fill_id=broker_fill_id,
        exec_id=exec_id,
        symbol=transition.symbol,
        filled_qty=transition.qty,
        fill_price=transition.fill_price,
        commission=transition.commission,
        fill_time=fill_time,
    )
    # INSERT OR IGNORE means no change if this was a duplicate fill by broker_fill_id/exec_id index.
    post_fills = order_repo.fetch_fills_for_order(sleeve_order_id=sleeve_order_id)
    if len(post_fills) == len(prior_fills):
        return SleeveFillApplicationResult(
            applied=False,
            reason="duplicate_fill_ignored",
            sleeve_order_id=int(sleeve_order_id),
            sleeve_id=order.sleeve_id,
            transition=None,
        )

    event_time = updated_at or utc_now_iso()
    ledger_reference_id = _build_ledger_reference_id(
        sleeve_order_id=sleeve_order_id,
        exec_id=exec_id,
        broker_fill_id=broker_fill_id,
        fill_time=fill_time,
    )

    ledger_repo.insert(
        sleeve_id=order.sleeve_id,
        entry_type=LEDGER_ENTRY_CASH_MOVEMENT,
        amount=transition.cash_delta,
        reference_type=LEDGER_REFERENCE_TYPE_SLEEVE_FILL,
        reference_id=ledger_reference_id,
        entry_time=fill_time,
        created_at=event_time,
    )
    if transition.commission > 0:
        ledger_repo.insert(
            sleeve_id=order.sleeve_id,
            entry_type=LEDGER_ENTRY_FEE,
            amount=-transition.commission,
            reference_type=LEDGER_REFERENCE_TYPE_SLEEVE_FILL,
            reference_id=ledger_reference_id,
            entry_time=fill_time,
            created_at=event_time,
        )
    if transition.realized_pnl_delta != 0:
        ledger_repo.insert(
            sleeve_id=order.sleeve_id,
            entry_type=LEDGER_ENTRY_REALIZED_PNL,
            amount=transition.realized_pnl_delta,
            reference_type=LEDGER_REFERENCE_TYPE_SLEEVE_FILL,
            reference_id=ledger_reference_id,
            entry_time=fill_time,
            created_at=event_time,
        )

    if transition.ending_qty > 0:
        position_repo.upsert(
            sleeve_id=order.sleeve_id,
            symbol=transition.symbol,
            qty=transition.ending_qty,
            avg_cost=transition.ending_avg_cost,
            market_value=transition.ending_market_value,
            unrealized_pnl=transition.ending_unrealized_pnl,
            updated_at=event_time,
        )
    else:
        position_repo.delete(sleeve_id=order.sleeve_id, symbol=transition.symbol)

    sleeve_repo.update_balances(
        sleeve_id=order.sleeve_id,
        current_cash=transition.ending_cash,
        current_equity=transition.ending_equity,
        updated_at=event_time,
    )
    return SleeveFillApplicationResult(
        applied=True,
        reason=None,
        sleeve_order_id=int(sleeve_order_id),
        sleeve_id=order.sleeve_id,
        transition=transition,
    )
