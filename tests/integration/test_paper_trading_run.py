"""Integration test for a signal-driven paper-trading run.

Covers the core capability "signal-driven paper execution" from
``docs/overview.md``. The test drives the ``run_accounts`` service entry that
the daily job calls, with the real selection, risk gate, submission, and
persistence path, and checks the resulting book bookkeeping: an order, a
position, a ledger entry, and the book's cash drawn down by the fill. Equity
snapshots and benchmark overlays are a separate daily-workflow step, not part
of ``run_accounts``, so they are out of scope here.

The controlled collaborators (window, reconciliation, broker) live in
``conftest.py``. The strategy signal itself is real.
"""

from __future__ import annotations

import sqlite3

import pytest

from tests.integration.conftest import FillEverythingBroker, rising_market
from tests.support.books import assign_test_book_strategy, build_book_env
from trading.domain.feature_provider import FeatureFetcherSet
from trading.repositories.books import BookRepository
from trading.repositories.ledger import LedgerRepository
from trading.repositories.orders import OrderRepository
from trading.repositories.positions import PositionRepository
from trading.services.auto_trading.inputs import run_accounts
from trading.services.strategy_catalog.seeding import seed_strategy_catalog

TICKER = "AAA"


@pytest.mark.usefixtures("open_market_runtime")
def test_run_accounts_executes_and_persists_a_signal_driven_buy(
    conn: sqlite3.Connection,
    fill_broker: FillEverythingBroker,
    policy_fetchers: FeatureFetcherSet,
) -> None:
    seed_strategy_catalog(conn)
    env = build_book_env(conn, start_equity=100_000.0)
    assign_test_book_strategy(conn, book_id=env.book_id, strategy_name="trend")
    # Execution knobs are book columns; size a buy that clears one share.
    conn.execute(
        "UPDATE books SET trade_size_pct = 10.0, max_position_pct = 50.0 WHERE id = ?",
        (env.book_id,),
    )
    conn.commit()

    results = run_accounts(
        conn,
        account_names=[env.account_name],
        market=rising_market(tickers=(TICKER,)),
        max_trades=1,
        fee=0.0,
        broker_factory=lambda _account: fill_broker,
        feature_fetchers=policy_fetchers,
    )

    assert len(results) == 1
    assert results[0].submitted_count == 1
    assert results[0].kill_switch_reasons == ()

    orders = OrderRepository(conn).fetch_for_book(book_id=env.book_id)
    assert len(orders) == 1
    assert orders[0].symbol == TICKER
    assert orders[0].side == "buy"
    assert orders[0].status == "filled"

    assert PositionRepository(conn).fetch(book_id=env.book_id, symbol=TICKER) is not None
    assert LedgerRepository(conn).fetch_for_book(book_id=env.book_id) != []
    assert fill_broker.disconnect_calls == 1

    # The book paid for the fill: its cash is drawn down from the starting equity.
    book = BookRepository(conn).fetch_by_id(book_id=env.book_id)
    assert book is not None
    assert book.current_cash < 100_000.0
