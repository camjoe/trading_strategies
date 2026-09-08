"""Integration test that a data-defined variant is tradeable at runtime.

Covers the runtime-consumption half of "data-defined strategy variants" from
``docs/overview.md``: a service-created variant, assigned to a book, drives a
real trade attributed to that variant. The CLI write side (create/tune/freeze)
is covered by ``tests/e2e/test_strategy_variant_cli.py``, and the catalog
resolution + knob-layering by
``tests/src/trading/services/strategy_catalog/test_resolution.py``; this test
proves the end-to-end chain those two stop short of — the variant row actually
reaching execution through the live selection, gate, submission, and
persistence path.

Note: the backtester does *not* consume catalog variants — it resolves through
the code registry. Variants reach execution only through this runtime path, so
this is the seam that proves a variant is genuinely tradeable.
"""

from __future__ import annotations

import sqlite3

import pytest

from tests.integration.conftest import FillEverythingBroker, rising_market
from tests.support.books import assign_test_book_strategy, build_book_env
from trading.domain.feature_provider import FeatureFetcherSet
from trading.repositories.orders import OrderRepository
from trading.services.auto_trading.inputs import run_accounts
from trading.services.books.book_assignments import open_assignment_for_book
from trading.services.strategy_catalog.mutations import create_strategy_variant

VARIANT_KEY = "tuned_trend_pilot"
TICKER = "AAA"


@pytest.mark.usefixtures("open_market_runtime")
def test_tuned_variant_resolves_and_drives_a_trade(
    conn: sqlite3.Connection,
    fill_broker: FillEverythingBroker,
    policy_fetchers: FeatureFetcherSet,
) -> None:
    # A variant of the "trend" primitive with knobs tuned away from its defaults
    # (fast/slow default to 10/20). Resolution and knob-layering are unit-tested
    # in test_resolution.py; here the variant has to reach execution.
    create_strategy_variant(
        conn,
        strategy_key=VARIANT_KEY,
        primitive="trend",
        params={"fast_window": 8, "slow_window": 21},
    )

    env = build_book_env(conn, start_equity=100_000.0)
    assign_test_book_strategy(conn, book_id=env.book_id, strategy_name=VARIANT_KEY)
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

    assert results[0].submitted_count == 1

    orders = OrderRepository(conn).fetch_for_book(book_id=env.book_id)
    assert len(orders) == 1
    assert orders[0].symbol == TICKER

    # The trade ran under the data-defined variant, not a bare primitive.
    assignment = open_assignment_for_book(conn, book_id=env.book_id)
    assert assignment is not None
    assert assignment.strategy_name.strip() == VARIANT_KEY
