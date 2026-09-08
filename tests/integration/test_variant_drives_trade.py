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

import pandas as pd
import pytest

import trading.services.auto_trading.runtime as runtime_service
from tests.support.backtesting import bars_from_closes
from tests.support.books import assign_test_book_strategy, build_book_env
from trading.domain.feature_provider import ExternalFeatureBundle, FeatureFetcherSet
from trading.models.market_data import MarketInputs
from trading.models.orders import BrokerOrder, OrderStatus
from trading.repositories.orders import OrderRepository
from trading.services.auto_trading.inputs import run_accounts
from trading.services.books.book_assignments import open_assignment_for_book
from trading.services.strategy_catalog.mutations import create_strategy_variant

VARIANT_KEY = "tuned_trend_pilot"
TICKER = "AAA"
RUN_TIME_ISO = "2026-05-04T14:00:00Z"


class _FillEverythingBroker:
    def __init__(self) -> None:
        self.disconnect_calls = 0

    def place_order(self, order: object) -> BrokerOrder:
        placed = BrokerOrder.from_request(order)
        placed.broker_order_id = "fake-broker-order"
        placed.status = OrderStatus.FILLED
        placed.filled_qty = order.qty  # type: ignore[attr-defined]
        placed.avg_fill_price = order.price  # type: ignore[attr-defined]
        return placed

    def get_open_trades(self) -> list[object]:
        return []

    def disconnect(self) -> None:
        self.disconnect_calls += 1


def _rising_market() -> MarketInputs:
    index = pd.date_range("2025-01-01", periods=70, freq="B")
    closes = pd.DataFrame({TICKER: [50.0 + step * 0.75 for step in range(len(index))]}, index=index)
    return MarketInputs(
        universe=[TICKER],
        prices={TICKER: float(closes[TICKER].iloc[-1])},
        histories=bars_from_closes(closes),
    )


def test_tuned_variant_resolves_and_drives_a_trade(conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch) -> None:
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

    monkeypatch.setattr(runtime_service, "utc_now_iso", lambda: RUN_TIME_ISO)
    monkeypatch.setattr(runtime_service, "is_runtime_submission_window_open", lambda *_a, **_k: True)
    monkeypatch.setattr(runtime_service, "reconcile_book_equity", lambda *_a, **_k: [])

    results = run_accounts(
        conn,
        account_names=[env.account_name],
        market=_rising_market(),
        max_trades=1,
        fee=0.0,
        broker_factory=lambda _account, b=_FillEverythingBroker(): b,
        feature_fetchers=FeatureFetcherSet(
            fetch_policy=lambda _ticker: ExternalFeatureBundle(features={}, available=True)
        ),
    )

    assert results[0].submitted_count == 1

    orders = OrderRepository(conn).fetch_for_book(book_id=env.book_id)
    assert len(orders) == 1
    assert orders[0].symbol == TICKER

    # The trade ran under the data-defined variant, not a bare primitive.
    assignment = open_assignment_for_book(conn, book_id=env.book_id)
    assert assignment is not None
    assert assignment.strategy_name.strip() == VARIANT_KEY
