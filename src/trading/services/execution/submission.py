from __future__ import annotations

import sqlite3
from collections.abc import Callable, Sequence

from common.time import utc_now_iso
from trading.domain.broker_connection import BrokerConnection
from trading.domain.sleeve_accounting import apply_sleeve_fill_transition
from trading.models.execution.book_trade_intent import BookTradeIntent
from trading.models.execution.submission_result import SubmissionResult
from trading.models.orders.broker_order import BrokerOrder, OrderStatus
from trading.repositories.ledger import LedgerRepository
from trading.repositories.orders import OrderRepository
from trading.repositories.positions import PositionRepository
from trading.services.execution.constants import KILL_SWITCH_REASON_BROKER_API_ANOMALY
from trading.services.execution.gate import PreSubmitGate

# Ledger vocabulary for a filled trade (a single book-keyed cash-movement entry).
# 2c (unified accounting) splits this into cash/fee/realized-pnl entries.
LEDGER_ENTRY_TYPE_TRADE = "trade"
LEDGER_REFERENCE_TYPE_ORDER = "order"

# Callback invoked after a book fill is persisted — the seam the routing phases use
# to bridge to record_trade during the cutover, before 2c unifies accounting.
OnFill = Callable[[BookTradeIntent, int, BrokerOrder], None]

# Broker statuses collapse onto the clean orders CHECK vocabulary
# ('submitted', 'partially_filled', 'filled', 'rejected', 'cancelled').
_CLEAN_STATUS_BY_BROKER_STATUS: dict[OrderStatus, str] = {
    OrderStatus.PENDING: "submitted",
    OrderStatus.SUBMITTED: "submitted",
    OrderStatus.ACCEPTED: "submitted",
    OrderStatus.PARTIALLY_FILLED: "partially_filled",
    OrderStatus.FILLED: "filled",
    OrderStatus.CANCELLED: "cancelled",
    OrderStatus.REJECTED: "rejected",
}


def _clean_order_status(status: OrderStatus) -> str:
    return _CLEAN_STATUS_BY_BROKER_STATUS[status]


def _apply_book_fill(
    *,
    book_id: int,
    order_id: int,
    side: str,
    symbol: str,
    fill_qty: float,
    fill_price: float,
    transaction_cost: float,
    fill_time: str,
    position_repo: PositionRepository,
    ledger_repo: LedgerRepository,
) -> None:
    """Update the book's position and append the trade ledger entry for a filled order.

    Reuses the book-agnostic fill math (avg-cost weighting, cash delta) from the
    domain layer rather than re-deriving it. ``transaction_cost`` folds the broker
    commission and the configured per-trade fee into the cost basis / cash delta.
    Only cash-independent fields are read back, so cash/realized-pnl are seeded at 0
    here — reconstructing the book's running cash is 2c's (unified accounting) job.
    """
    current = position_repo.fetch(book_id=book_id, symbol=symbol)
    position_qty = current.qty if current is not None else 0.0
    position_avg_cost = current.avg_cost if current is not None else 0.0

    transition = apply_sleeve_fill_transition(
        side=side,
        symbol=symbol,
        qty=fill_qty,
        fill_price=fill_price,
        commission=transaction_cost,
        requested_price=None,
        position_qty=position_qty,
        position_avg_cost=position_avg_cost,
        cash=0.0,
        realized_pnl=0.0,
    )

    if transition.ending_qty > 0:
        position_repo.upsert(
            book_id=book_id,
            symbol=transition.symbol,
            qty=transition.ending_qty,
            avg_cost=transition.ending_avg_cost,
            market_value=transition.ending_market_value,
            unrealized_pnl=transition.ending_unrealized_pnl,
            updated_at=fill_time,
        )
    else:
        position_repo.delete(book_id=book_id, symbol=transition.symbol)

    ledger_repo.insert(
        book_id=book_id,
        entry_type=LEDGER_ENTRY_TYPE_TRADE,
        amount=transition.cash_delta,
        reference_type=LEDGER_REFERENCE_TYPE_ORDER,
        reference_id=str(order_id),
        entry_time=fill_time,
        created_at=fill_time,
    )


def submit_book_intents(
    conn: sqlite3.Connection,
    *,
    book_id: int,
    account_id: int,
    intents: Sequence[BookTradeIntent],
    broker: BrokerConnection,
    gate: PreSubmitGate,
    fee: float,
    on_fill: OnFill | None = None,
) -> SubmissionResult:
    """Submit one book's intents: gate → place → persist clean tables → on-fill.

    The single submission path shared by every book. For each approved intent:
    place the order via the injected ``broker``, persist to the clean ``orders`` /
    ``order_fills`` tables, and on a ``FILLED`` status update ``positions`` and
    append a ``ledger`` trade entry — all keyed by ``book_id``. A pre-submit kill
    switch (from the gate) holds the whole book; a broker-API exception mid-loop
    appends the anomaly reason and stops, mirroring the legacy sleeve path.
    """
    gate_result = gate.evaluate(conn, account_id=account_id, intents=intents)
    kill_switch_reasons = list(gate_result.kill_switch_reasons)
    blocked_count = len(gate_result.blocked_intents)
    rescaled_count = len(gate_result.rescaled_intents)

    # A kill switch holds the entire book: submit nothing (safety strengthens for all books).
    if kill_switch_reasons:
        return SubmissionResult(
            kill_switch_reasons=kill_switch_reasons,
            blocked_count=blocked_count,
            rescaled_count=rescaled_count,
        )

    order_repo = OrderRepository(conn)
    position_repo = PositionRepository(conn)
    ledger_repo = LedgerRepository(conn)

    order_ids: list[int] = []
    filled_count = 0
    for intent in gate_result.approved_intents:
        submitted_at = utc_now_iso()
        broker_order = BrokerOrder(
            account_id=account_id,
            ticker=intent.symbol,
            side=intent.side,
            qty=float(intent.qty),
            price=float(intent.requested_price or 0.0),
        )
        try:
            placed = broker.place_order(broker_order)
        except Exception:
            kill_switch_reasons.append(KILL_SWITCH_REASON_BROKER_API_ANOMALY)
            break

        updated_at = placed.updated_at or utc_now_iso()
        order_id = order_repo.insert(
            book_id=book_id,
            account_id=account_id,
            strategy_id=intent.strategy_id,
            broker_order_id=placed.broker_order_id,
            symbol=intent.symbol,
            side=intent.side,
            qty=float(intent.qty),
            order_type=intent.order_type,
            time_in_force=intent.time_in_force,
            requested_price=intent.requested_price,
            status=_clean_order_status(placed.status),
            filled_qty=float(placed.filled_qty),
            avg_fill_price=placed.avg_fill_price,
            commission=float(placed.commission),
            submitted_at=placed.submitted_at or submitted_at,
            updated_at=updated_at,
        )
        order_ids.append(order_id)

        for fill in placed.fills:
            order_repo.insert_fill(
                order_id=order_id,
                filled_qty=float(fill.filled_qty),
                fill_price=float(fill.fill_price),
                fill_time=fill.fill_time,
                commission=float(fill.commission),
                broker_fill_id=placed.broker_order_id,
                exec_id=fill.exec_id,
            )

        if placed.status == OrderStatus.FILLED:
            fill_price = (
                float(placed.avg_fill_price)
                if placed.avg_fill_price is not None
                else float(intent.requested_price or 0.0)
            )
            fill_qty = float(placed.filled_qty) if placed.filled_qty > 0 else float(intent.qty)
            fill_time = placed.updated_at or updated_at
            _apply_book_fill(
                book_id=book_id,
                order_id=order_id,
                side=intent.side,
                symbol=intent.symbol,
                fill_qty=fill_qty,
                fill_price=fill_price,
                transaction_cost=float(placed.commission) + float(fee),
                fill_time=fill_time,
                position_repo=position_repo,
                ledger_repo=ledger_repo,
            )
            filled_count += 1
            if on_fill is not None:
                on_fill(intent, order_id, placed)

    return SubmissionResult(
        order_ids=order_ids,
        submitted_count=len(order_ids),
        filled_count=filled_count,
        blocked_count=blocked_count,
        rescaled_count=rescaled_count,
        kill_switch_reasons=kill_switch_reasons,
    )
