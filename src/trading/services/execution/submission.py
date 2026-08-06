from __future__ import annotations

import sqlite3
from collections.abc import Callable, Sequence

from common.time import utc_now_iso
from trading.domain.book_accounting import apply_book_fill_transition
from trading.domain.broker_connection import BrokerConnection
from trading.models.execution import BookTradeIntent, SubmissionResult
from trading.models.orders import BrokerOrder, OrderStatus
from trading.repositories.books import BookRepository
from trading.repositories.ledger import LedgerRepository
from trading.repositories.orders import OrderRepository
from trading.repositories.positions import PositionRepository
from trading.repositories.unit_of_work import unit_of_work
from trading.services.execution.constants import KILL_SWITCH_REASON_BROKER_API_ANOMALY
from trading.services.execution.gate import PreSubmitGate
from trading.services.operational_settings.enforcement import RuntimeTradeThrottleExceededError

# Clean cash-flow ledger vocabulary: each entry is a cash movement, so a book's
# cash = starting cash + Σ(ledger.amount). A fill posts a gross `trade` entry plus a
# `fee` entry; the two sum to the net cash delta. `realized_pnl`/`cash_movement` from
# the legacy ledger are intentionally NOT used — the clean `ledger` CHECK forbids them,
# and realized P&L is derived for reporting, not a cash flow.
LEDGER_ENTRY_TYPE_TRADE = "trade"
LEDGER_ENTRY_TYPE_FEE = "fee"
LEDGER_REFERENCE_TYPE_ORDER = "order"

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


def clean_order_status(status: OrderStatus) -> str:
    return _CLEAN_STATUS_BY_BROKER_STATUS[status]


def apply_book_fill(
    conn: sqlite3.Connection,
    *,
    book_id: int,
    order_id: int,
    side: str,
    symbol: str,
    fill_qty: float,
    fill_price: float,
    transaction_cost: float,
    fill_time: str,
) -> None:
    """Apply a filled order to the book: position, cash-flow ledger, and balances.

    Shared by the synchronous submission path (:func:`submit_book_intents`) and the
    async open-order reconciliation. Reuses the book-agnostic fill math (avg-cost
    weighting, cash delta) from the domain layer rather than re-deriving it.
    ``transaction_cost`` folds the broker commission (and, on the synchronous path,
    the configured per-trade fee) into the cost basis / cash delta. The ledger is a
    cash-flow ledger (gross ``trade`` + ``fee``, summing to the net cash delta);
    ``books.current_cash`` is authoritative and updated incrementally, while
    ``current_equity`` is marked at fill price here (the NAV pass re-marks to market).

    Not idempotent — callers must apply each execution exactly once (the submission
    path fills once; reconciliation dedups on ``order_fills.exec_id`` first).
    """
    book_repo = BookRepository(conn)
    position_repo = PositionRepository(conn)
    ledger_repo = LedgerRepository(conn)

    current = position_repo.fetch(book_id=book_id, symbol=symbol)
    position_qty = current.qty if current is not None else 0.0
    position_avg_cost = current.avg_cost if current is not None else 0.0

    transition = apply_book_fill_transition(
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

    # The position, ledger, and balance writes are one atomic unit: a fill's
    # recorded existence and its cash/position effects must land together, or the
    # exec_id dedup would skip a re-run and leave the effect permanently unapplied.
    with unit_of_work(conn):
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

        # Cash-flow ledger: gross trade cash (sign by side) + a separate fee entry; the
        # two sum to transition.cash_delta (the net applied to book cash).
        gross_cash = float(fill_qty) * float(fill_price)
        ledger_repo.insert(
            book_id=book_id,
            entry_type=LEDGER_ENTRY_TYPE_TRADE,
            amount=-gross_cash if transition.side == "buy" else gross_cash,
            reference_type=LEDGER_REFERENCE_TYPE_ORDER,
            reference_id=str(order_id),
            entry_time=fill_time,
            created_at=fill_time,
        )
        if transaction_cost > 0:
            ledger_repo.insert(
                book_id=book_id,
                entry_type=LEDGER_ENTRY_TYPE_FEE,
                amount=-float(transaction_cost),
                reference_type=LEDGER_REFERENCE_TYPE_ORDER,
                reference_id=str(order_id),
                entry_time=fill_time,
                created_at=fill_time,
            )

        # Book balances: cash is authoritative (incremental); equity is cash + the sum of
        # position market values (fill-marked until the NAV-marking pass in 2c-2).
        book = book_repo.fetch_by_id(book_id=book_id)
        prior_cash = book.current_cash if book is not None else 0.0
        new_cash = prior_cash + transition.cash_delta
        market_value = sum(position.market_value for position in position_repo.fetch_for_book(book_id=book_id))
        book_repo.update_balances(
            book_id=book_id,
            current_cash=new_cash,
            current_equity=new_cash + market_value,
            updated_at=fill_time,
        )

        # A sell realizes P&L against the position's average cost; persist it on the
        # order so daily-metrics can derive hit_rate/expectancy. Buys realize nothing
        # (delta is 0.0) and are left NULL, so NOT NULL marks a closing trade.
        if transition.side == "sell":
            OrderRepository(conn).add_realized_pnl_delta(
                order_id=order_id,
                realized_pnl_delta=transition.realized_pnl_delta,
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
    enforce_throttle: Callable[[], None] | None = None,
) -> SubmissionResult:
    """Submit one book's intents: gate → place → persist clean tables.

    The single submission path shared by every book. For each approved intent:
    place the order via the injected ``broker``, persist to the clean ``orders`` /
    ``order_fills`` tables, and on a ``FILLED`` status update ``positions``, the
    cash-flow ``ledger``, and the book's ``current_cash``/``current_equity`` — all
    keyed by ``book_id``. A pre-submit kill switch (from the gate) holds the whole
    book; a broker-API exception mid-loop appends the anomaly reason and stops,
    mirroring the legacy submission path.
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

    order_ids: list[int] = []
    filled_count = 0
    throttled = False
    for intent in gate_result.approved_intents:
        # Between orders, not once per book: a book emits several trades per
        # run since the per-book budget became real, and the per-minute cap
        # exists to pace the requests themselves.
        if enforce_throttle is not None:
            try:
                enforce_throttle()
            except RuntimeTradeThrottleExceededError:
                throttled = True
                break
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
        # One transaction per order: the order row, its fill rows, and the book
        # accounting land together or not at all. The broker call above stays
        # outside the transaction — network I/O must not hold a write lock.
        with unit_of_work(conn):
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
                status=clean_order_status(placed.status),
                filled_qty=float(placed.filled_qty),
                avg_fill_price=placed.avg_fill_price,
                commission=float(placed.commission),
                submitted_at=placed.submitted_at or submitted_at,
                updated_at=updated_at,
                status_reason=placed.status_reason,
            )

            # Fill rows are the only execution history (the trades table was retired
            # in revision 0006), so their commissions must sum to the transaction
            # cost applied to the book: the configured per-trade fee rides on the
            # first fill of a synchronously filled order.
            is_filled = placed.status == OrderStatus.FILLED
            for fill_index, fill in enumerate(placed.fills):
                fee_share = float(fee) if is_filled and fill_index == 0 else 0.0
                order_repo.insert_fill(
                    order_id=order_id,
                    filled_qty=float(fill.filled_qty),
                    fill_price=float(fill.fill_price),
                    fill_time=fill.fill_time,
                    commission=float(fill.commission) + fee_share,
                    exec_id=fill.exec_id,
                )

            if is_filled:
                fill_price = (
                    float(placed.avg_fill_price)
                    if placed.avg_fill_price is not None
                    else float(intent.requested_price or 0.0)
                )
                fill_qty = float(placed.filled_qty) if placed.filled_qty > 0 else float(intent.qty)
                fill_time = placed.updated_at or updated_at
                if not placed.fills:
                    # A FILLED order must leave a fill row — synthesize one from the
                    # aggregate so derived account history stays complete.
                    order_repo.insert_fill(
                        order_id=order_id,
                        filled_qty=fill_qty,
                        fill_price=fill_price,
                        fill_time=fill_time,
                        commission=float(placed.commission) + float(fee),
                        exec_id=None,
                    )
                apply_book_fill(
                    conn,
                    book_id=book_id,
                    order_id=order_id,
                    side=intent.side,
                    symbol=intent.symbol,
                    fill_qty=fill_qty,
                    fill_price=fill_price,
                    transaction_cost=float(placed.commission) + float(fee),
                    fill_time=fill_time,
                )

        order_ids.append(order_id)
        if placed.status == OrderStatus.FILLED:
            filled_count += 1

    return SubmissionResult(
        order_ids=order_ids,
        submitted_count=len(order_ids),
        filled_count=filled_count,
        blocked_count=blocked_count,
        rescaled_count=rescaled_count,
        kill_switch_reasons=kill_switch_reasons,
        throttled=throttled,
    )
