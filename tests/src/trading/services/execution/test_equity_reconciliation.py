from __future__ import annotations

import pytest

from tests.src.trading.services.execution.helpers import insert_book_equity_snapshot
from tests.support.books import ensure_default_book_id
from tests.support.repositories import insert_repository_account
from trading.models.execution import BookTradeIntent
from trading.models.orders import BrokerOrder, OrderRequest, OrderStatus
from trading.repositories.books import BookRepository
from trading.repositories.snapshots import EquitySnapshotRepository
from trading.services.execution.constants import (
    KILL_SWITCH_REASON_RECONCILIATION_MISMATCH,
    KILL_SWITCH_REASON_RECONCILIATION_SNAPSHOT_MISSING,
)
from trading.services.execution.gate import AllowAllGate
from trading.services.execution.ledger.mutations import record_trade
from trading.services.execution.ledger.queries import load_account_state
from trading.services.execution.nav import mark_book_to_market
from trading.services.execution.equity_reconciliation import reconcile_book_equity
from trading.services.execution.submission import submit_book_intents

NOW = "2026-07-05T12:00:00Z"


class _FilledBroker:
    def place_order(self, order: OrderRequest) -> BrokerOrder:
        placed = BrokerOrder.from_request(order)
        placed.broker_order_id = "B1"
        placed.status = OrderStatus.FILLED
        placed.filled_qty = order.qty
        placed.avg_fill_price = order.price
        placed.submitted_at = NOW
        placed.updated_at = NOW
        return placed


def _account_book(conn, *, equity: float) -> tuple[int, int]:
    account_id = insert_repository_account(conn, name="recon_acct")
    book_id = BookRepository(conn).insert(
        account_id=account_id,
        name="default",
        is_default=1,
        start_equity=equity,
        current_cash=equity,
        current_equity=equity,
        created_at="2026-07-05T00:00:00Z",
        updated_at="2026-07-05T00:00:00Z",
    )
    return account_id, book_id


def _snapshot(conn, book_id: int, *, equity: float, snapshot_time: str = NOW) -> None:
    insert_book_equity_snapshot(conn, book_id, equity=equity, snapshot_time=snapshot_time)


# --- unit ------------------------------------------------------------------


def test_missing_snapshot_reports_missing(conn):
    account_id, _ = _account_book(conn, equity=10_000.0)
    assert reconcile_book_equity(conn, account_id=account_id) == [KILL_SWITCH_REASON_RECONCILIATION_SNAPSHOT_MISSING]


def test_within_tolerance_is_clean(conn):
    account_id, book_id = _account_book(conn, equity=10_000.0)
    _snapshot(conn, book_id, equity=10_000.0)
    assert reconcile_book_equity(conn, account_id=account_id) == []


def test_equity_mismatch_reports_mismatch(conn):
    account_id, book_id = _account_book(conn, equity=10_000.0)
    _snapshot(conn, book_id, equity=9_000.0)
    assert reconcile_book_equity(conn, account_id=account_id) == [KILL_SWITCH_REASON_RECONCILIATION_MISMATCH]


# --- integration: fill (2c-1) → mark (2c-2) → reconcile (2c-3) --------------


def test_fill_then_mark_then_reconcile_pipeline(conn):
    account_id, book_id = _account_book(conn, equity=10_000.0)

    submit_book_intents(
        conn,
        book_id=book_id,
        account_id=account_id,
        intents=[
            BookTradeIntent(
                book_id=book_id,
                account_id=account_id,
                strategy_id=None,
                symbol="AAPL",
                side="buy",
                qty=10.0,
                requested_price=100.0,
            )
        ],
        broker=_FilledBroker(),
        gate=AllowAllGate(),
        fee=0.0,
    )
    # After the fill: cash 9_000, position fill-marked at 1_000 → equity 10_000.
    mark_book_to_market(conn, book_id=book_id, prices={"AAPL": 120.0}, as_of=NOW)
    # After marking: equity = 9_000 + 10 * 120 = 10_200.
    book = BookRepository(conn).fetch_by_id(book_id=book_id)
    assert book is not None
    assert book.current_equity == pytest.approx(10_200.0)

    # A market-marked snapshot agrees with the NAV-marked book equity → clean.
    _snapshot(conn, book_id, equity=10_200.0)
    assert reconcile_book_equity(conn, account_id=account_id) == []


# --- 2c-4: confirm the clean book path and the independent account/trades path agree ----


def test_book_and_account_accounting_agree_and_reconcile(conn):
    """One fill through both accounting systems must reconcile at cutover.

    The reconciliation snapshot stays an INDEPENDENT measure (account/trades roll-up,
    later the broker) — never derived from book balances, which would make the check a
    tautology. This proves the two independent systems agree on the same fill + prices.
    """
    account_name = "confirm_acct"
    account_id = insert_repository_account(conn, name=account_name, initial_cash=10_000.0)
    book_id = ensure_default_book_id(conn, account_id)  # bootstraps the book at initial_cash

    # The same buy through both paths: the legacy account ledger and the clean book path.
    record_trade(
        conn,
        account_name=account_name,
        side="buy",
        ticker="AAPL",
        qty=10.0,
        price=100.0,
        fee=0.0,
        trade_time=NOW,
        note=None,
    )
    submit_book_intents(
        conn,
        book_id=book_id,
        account_id=account_id,
        intents=[
            BookTradeIntent(
                book_id=book_id,
                account_id=account_id,
                strategy_id=None,
                symbol="AAPL",
                side="buy",
                qty=10.0,
                requested_price=100.0,
            )
        ],
        broker=_FilledBroker(),
        gate=AllowAllGate(),
        fee=0.0,
    )

    prices = {"AAPL": 110.0}
    nav = mark_book_to_market(conn, book_id=book_id, prices=prices, as_of=NOW)

    # Independent account/trades equity, marked at the same prices.
    state = load_account_state(conn, account_id=account_id, initial_cash=10_000.0)
    account_equity = state.cash + sum(qty * prices[symbol] for symbol, qty in state.positions.items())

    assert nav.current_equity == pytest.approx(account_equity)

    # Snapshot written from the INDEPENDENT account source → reconciles clean.
    EquitySnapshotRepository(conn).insert_for_book(
        book_id=ensure_default_book_id(conn, account_id),
        snapshot_time=NOW,
        cash=state.cash,
        market_value=account_equity - state.cash,
        equity=account_equity,
        realized_pnl=0.0,
        unrealized_pnl=0.0,
    )
    assert reconcile_book_equity(conn, account_id=account_id) == []
