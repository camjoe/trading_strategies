from __future__ import annotations

import pytest

from trading.models.execution.book_trade_intent import BookTradeIntent
from trading.models.orders.broker_order import BrokerOrder, OrderStatus
from trading.repositories.books import BookRepository
from trading.repositories.snapshots import EquitySnapshotRepository
from trading.services.execution.constants import (
    KILL_SWITCH_REASON_RECONCILIATION_MISMATCH,
    KILL_SWITCH_REASON_RECONCILIATION_SNAPSHOT_MISSING,
    KILL_SWITCH_REASON_STALE_RECONCILIATION_SNAPSHOT,
)
from trading.services.execution.gate import AllowAllGate
from trading.services.execution.nav import mark_book_to_market
from trading.services.execution.reconciliation import reconcile_book_equity
from trading.services.execution.submission import submit_book_intents
from tests.support.repositories import insert_repository_account

NOW = "2026-07-05T12:00:00Z"


class _FilledBroker:
    def place_order(self, order: BrokerOrder) -> BrokerOrder:
        order.broker_order_id = "B1"
        order.status = OrderStatus.FILLED
        order.filled_qty = order.qty
        order.avg_fill_price = order.price
        order.submitted_at = NOW
        order.updated_at = NOW
        order.fills = []
        return order


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
    EquitySnapshotRepository(conn).insert_for_book(
        book_id=book_id,
        snapshot_time=snapshot_time,
        cash=equity,
        market_value=0.0,
        equity=equity,
        realized_pnl=0.0,
        unrealized_pnl=0.0,
    )


# --- unit ------------------------------------------------------------------


def test_missing_snapshot_reports_missing(conn):
    account_id, _ = _account_book(conn, equity=10_000.0)
    assert reconcile_book_equity(conn, account_id=account_id, now_iso=NOW) == [
        KILL_SWITCH_REASON_RECONCILIATION_SNAPSHOT_MISSING
    ]


def test_within_tolerance_is_clean(conn):
    account_id, book_id = _account_book(conn, equity=10_000.0)
    _snapshot(conn, book_id, equity=10_000.0)
    assert reconcile_book_equity(conn, account_id=account_id, now_iso=NOW) == []


def test_equity_mismatch_reports_mismatch(conn):
    account_id, book_id = _account_book(conn, equity=10_000.0)
    _snapshot(conn, book_id, equity=9_000.0)
    assert reconcile_book_equity(conn, account_id=account_id, now_iso=NOW) == [
        KILL_SWITCH_REASON_RECONCILIATION_MISMATCH
    ]


def test_stale_snapshot_reports_stale(conn):
    account_id, book_id = _account_book(conn, equity=10_000.0)
    # Equity agrees (no mismatch), but the snapshot is far older than the 6h window.
    _snapshot(conn, book_id, equity=10_000.0, snapshot_time="2026-07-01T00:00:00Z")
    assert reconcile_book_equity(conn, account_id=account_id, now_iso=NOW) == [
        KILL_SWITCH_REASON_STALE_RECONCILIATION_SNAPSHOT
    ]


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
    assert reconcile_book_equity(conn, account_id=account_id, now_iso=NOW) == []
