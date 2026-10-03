"""Integration test for multi-book execution within one account.

Covers the core capability "multi-book accounts" from ``docs/overview.md``:
one broker account hosts several independent books, each trading its own
universe. The test runs two active books through the real selection, risk gate,
submission, and persistence path, and checks each book's order is routed to and
persisted on its own book. The controlled collaborators (window, reconciliation,
broker) live in ``conftest.py``; the ``trend`` signal is real.

The account-wide trade budget cap and the book claim order are unit-tested in
``tests/src/trading/services/execution/selection/test_book_intents.py`` (the
``account_cap`` / ``account_trade_budget`` cases); this test uses a
non-binding budget so both books trade, and proves the multi-book submission
and per-book persistence those selection tests stop short of.
"""

from __future__ import annotations

import sqlite3

import pytest

from tests.integration.conftest import FillEverythingBroker, rising_market
from tests.support.books import assign_test_book_strategy, build_book_env, insert_test_book
from trading.domain.feature_provider import FeatureFetcherSet
from trading.repositories.orders import OrderRepository
from trading.repositories.snapshots import EquitySnapshotRepository
from trading.services.auto_trading.inputs import run_accounts
from trading.services.strategy_catalog.seeding import seed_strategy_catalog


def _size_book(conn: sqlite3.Connection, book_id: int, symbols: str) -> None:
    conn.execute(
        "UPDATE books SET trade_size_pct = 10.0, max_position_pct = 50.0, trade_symbols = ? WHERE id = ?",
        (symbols, book_id),
    )


@pytest.mark.usefixtures("open_market_runtime")
def test_two_books_each_execute_their_own_symbol(
    conn: sqlite3.Connection,
    fill_broker: FillEverythingBroker,
    policy_fetchers: FeatureFetcherSet,
) -> None:
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

    results = run_accounts(
        conn,
        account_names=[env.account_name],
        market=rising_market(tickers=("AAA", "BBB")),
        max_trades=2,
        fee=0.0,
        broker_factory=lambda _account: fill_broker,
        feature_fetchers=policy_fetchers,
    )

    assert results[0].submitted_count == 2

    orders_a = OrderRepository(conn).fetch_for_book(book_id=book_a)
    orders_b = OrderRepository(conn).fetch_for_book(book_id=book_b)
    assert [order.symbol for order in orders_a] == ["AAA"]
    assert [order.symbol for order in orders_b] == ["BBB"]
