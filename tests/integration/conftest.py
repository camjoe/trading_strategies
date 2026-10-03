"""Shared fixtures for the signal-driven execution integration tests.

The three trading-pipeline tests all drive ``run_accounts`` over a real book
with real signals, and each controls the same three collaborators: the
market-hours window, the equity reconciliation pre-flight, and the broker.
These fixtures hold that common scaffolding so each test expresses only its
distinct setup and assertions.
"""

from __future__ import annotations

import pandas as pd
import pytest

import trading.services.auto_trading.runtime as runtime_service
from tests.support.backtesting import bars_from_closes
from trading.domain.feature_provider import ExternalFeatureBundle, FeatureFetcherSet
from trading.models.market_data import MarketInputs
from trading.models.orders import BrokerOrder, OrderStatus

RUNTIME_NOW_ISO = "2026-05-04T14:00:00Z"


class FillEverythingBroker:
    """A broker that fills each order at its requested price.

    Each fill gets a unique ``broker_order_id`` so a run that submits more than
    one order does not trip the ``(account_id, broker_order_id)`` uniqueness
    constraint.
    """

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


def rising_market(*, tickers: tuple[str, ...] = ("AAA",)) -> MarketInputs:
    """MarketInputs over one or more strictly rising 70-bar histories.

    A rising series makes the ``trend`` primitive return buy
    (``close > fast_ma > slow_ma``). Each ticker starts from a different base so
    several can trade in one run without sharing a price.
    """
    index = pd.date_range("2025-01-01", periods=70, freq="B")
    closes = pd.DataFrame(
        {
            ticker: [50.0 + column * 10.0 + step * 0.75 for step in range(len(index))]
            for column, ticker in enumerate(tickers)
        },
        index=index,
    )
    return MarketInputs(
        universe=list(tickers),
        prices={ticker: float(closes[ticker].iloc[-1]) for ticker in tickers},
        histories=bars_from_closes(closes),
    )


@pytest.fixture
def fill_broker() -> FillEverythingBroker:
    return FillEverythingBroker()


@pytest.fixture
def open_market_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force the submission window open, freeze the clock, and stub reconciliation clean.

    These isolate a run from the wall clock and the equity reconciliation
    pre-flight (tested separately); every other collaborator stays real.
    """
    monkeypatch.setattr(runtime_service, "utc_now_iso", lambda: RUNTIME_NOW_ISO)
    monkeypatch.setattr(runtime_service, "is_runtime_submission_window_open", lambda *_a, **_k: True)
    monkeypatch.setattr(runtime_service, "reconcile_book_equity", lambda *_a, **_k: [])


@pytest.fixture
def policy_fetchers() -> FeatureFetcherSet:
    """The composition root's shape: policy supplied, news and social absent."""
    return FeatureFetcherSet(fetch_policy=lambda _ticker: ExternalFeatureBundle(features={}, available=True))
