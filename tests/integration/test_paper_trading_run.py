"""Integration test for a signal-driven paper-trading run.

Covers the core capability "signal-driven paper execution" from
``docs/overview.md``. The test drives the ``run_accounts`` service entry that
the daily job calls, with the real selection, risk gate, submission, and
persistence path, and checks the resulting book bookkeeping: an order, a
position, a ledger entry, and the book's cash drawn down by the fill. Equity
snapshots and benchmark overlays are a separate daily-workflow step, not part
of ``run_accounts``, so they are out of scope here.

Only three collaborators are controlled:

- the market-hours window is forced open, so the run does not depend on when
  the test runs;
- the pre-flight equity reconciliation is stubbed clean, because it has its
  own dedicated tests and a fresh book's balances would otherwise trip it;
- the broker is a fill-everything fake, because a real broker is out of scope.

The strategy signal itself is real: a strictly rising price history makes the
``trend`` primitive return ``buy`` (``close > fast_ma > slow_ma``).
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
from trading.repositories.books import BookRepository
from trading.repositories.ledger import LedgerRepository
from trading.repositories.orders import OrderRepository
from trading.repositories.positions import PositionRepository
from trading.services.auto_trading.inputs import run_accounts
from trading.services.strategy_catalog.seeding import seed_strategy_catalog

RUN_TIME_ISO = "2026-05-04T14:00:00Z"
TICKER = "AAA"


class _FillEverythingBroker:
    """A broker that fills each order at its requested price."""

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


def _policy_only_fetchers() -> FeatureFetcherSet:
    return FeatureFetcherSet(fetch_policy=lambda _ticker: ExternalFeatureBundle(features={}, available=True))


def test_run_accounts_executes_and_persists_a_signal_driven_buy(
    conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
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

    monkeypatch.setattr(runtime_service, "utc_now_iso", lambda: RUN_TIME_ISO)
    monkeypatch.setattr(runtime_service, "is_runtime_submission_window_open", lambda *_a, **_k: True)
    monkeypatch.setattr(runtime_service, "reconcile_book_equity", lambda *_a, **_k: [])
    broker = _FillEverythingBroker()

    results = run_accounts(
        conn,
        account_names=[env.account_name],
        market=_rising_market(),
        max_trades=1,
        fee=0.0,
        broker_factory=lambda _account, b=broker: b,
        feature_fetchers=_policy_only_fetchers(),
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
    assert broker.disconnect_calls == 1

    # The book paid for the fill: its cash is drawn down from the starting equity.
    book = BookRepository(conn).fetch_by_id(book_id=env.book_id)
    assert book is not None
    assert book.current_cash < 100_000.0
