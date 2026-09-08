"""Integration test for multi-book execution within one account.

Covers the core capability "multi-book accounts" from ``docs/overview.md``:
one broker account hosts several independent books that each trade their own
strategy and universe, and the account-wide trade budget is shared across
them. The test runs two active books through the real selection, risk gate,
submission, and persistence path, and checks each book executed its own
symbol. Only the market-hours window, the reconciliation pre-flight, and the
broker are controlled; the ``trend`` signal is real.
"""

from __future__ import annotations

import sqlite3

import pandas as pd
import pytest

import trading.services.auto_trading.runtime as runtime_service
from tests.support.backtesting import bars_from_closes
from tests.support.books import assign_test_book_strategy, build_book_env, insert_test_book
from trading.domain.feature_provider import ExternalFeatureBundle, FeatureFetcherSet
from trading.models.market_data import MarketInputs
from trading.models.orders import BrokerOrder, OrderStatus
from trading.repositories.orders import OrderRepository
from trading.repositories.snapshots import EquitySnapshotRepository
from trading.services.auto_trading.inputs import run_accounts
from trading.services.strategy_catalog.seeding import seed_strategy_catalog

RUN_TIME_ISO = "2026-05-04T14:00:00Z"


class _FillEverythingBroker:
    def __init__(self) -> None:
        self.disconnect_calls = 0
        self._order_seq = 0

    def place_order(self, order: object) -> BrokerOrder:
        placed = BrokerOrder.from_request(order)
        self._order_seq += 1
        placed.broker_order_id = f"fake-broker-order-{self._order_seq}"
        placed.status = OrderStatus.FILLED
        placed.filled_qty = order.qty  # type: ignore[attr-defined]
        placed.avg_fill_price = order.price  # type: ignore[attr-defined]
        return placed

    def get_open_trades(self) -> list[object]:
        return []

    def disconnect(self) -> None:
        self.disconnect_calls += 1


def _rising_bars(symbol: str, *, base: float) -> pd.DataFrame:
    index = pd.date_range("2025-01-01", periods=70, freq="B")
    closes = pd.DataFrame({symbol: [base + step * 0.75 for step in range(len(index))]}, index=index)
    return bars_from_closes(closes)[symbol]


def _size_book(conn: sqlite3.Connection, book_id: int, symbols: str) -> None:
    conn.execute(
        "UPDATE books SET trade_size_pct = 10.0, max_position_pct = 50.0, trade_symbols = ? WHERE id = ?",
        (symbols, book_id),
    )


def test_two_books_each_execute_their_own_symbol(conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch) -> None:
    seed_strategy_catalog(conn)
    env = build_book_env(conn, start_equity=100_000.0)
    book_a = env.book_id
    book_b = insert_test_book(conn, account_id=env.account_id, name="second", start_equity=100_000.0)
    EquitySnapshotRepository(conn).insert_for_book(
        book_id=book_b,
        snapshot_time="2026-05-03T13:59:00Z",
        cash=100_000.0,
        market_value=0.0,
        equity=100_000.0,
        realized_pnl=0.0,
        unrealized_pnl=0.0,
    )
    for book_id in (book_a, book_b):
        assign_test_book_strategy(conn, book_id=book_id, strategy_name="trend")
    _size_book(conn, book_a, '["AAA"]')
    _size_book(conn, book_b, '["BBB"]')
    conn.commit()

    market = MarketInputs(
        universe=["AAA", "BBB"],
        prices={"AAA": 100.0, "BBB": 100.0},
        histories={"AAA": _rising_bars("AAA", base=50.0), "BBB": _rising_bars("BBB", base=60.0)},
    )

    monkeypatch.setattr(runtime_service, "utc_now_iso", lambda: RUN_TIME_ISO)
    monkeypatch.setattr(runtime_service, "is_runtime_submission_window_open", lambda *_a, **_k: True)
    monkeypatch.setattr(runtime_service, "reconcile_book_equity", lambda *_a, **_k: [])
    broker = _FillEverythingBroker()

    results = run_accounts(
        conn,
        account_names=[env.account_name],
        market=market,
        max_trades=2,
        fee=0.0,
        broker_factory=lambda _account, b=broker: b,
        feature_fetchers=FeatureFetcherSet(
            fetch_policy=lambda _ticker: ExternalFeatureBundle(features={}, available=True)
        ),
    )

    assert results[0].submitted_count == 2

    orders_a = OrderRepository(conn).fetch_for_book(book_id=book_a)
    orders_b = OrderRepository(conn).fetch_for_book(book_id=book_b)
    assert [order.symbol for order in orders_a] == ["AAA"]
    assert [order.symbol for order in orders_b] == ["BBB"]
