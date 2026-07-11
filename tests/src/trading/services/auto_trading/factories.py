from __future__ import annotations

from typing import Callable, Mapping
from unittest.mock import Mock

from trading.domain.feature_provider import ExternalFeatureBundle, FeatureFetcherSet
from trading.models.accounts.account_state import AccountState
from trading.models.orders.broker_order import OrderStatus
from tests.support.account_records import make_account_record

MARKET_OPEN_TIME_ISO = "2026-03-14T14:00:00Z"
MARKET_CLOSED_TIME_ISO = "2026-03-15T15:00:00Z"


def make_auto_trading_account(**overrides: object):
    values: dict[str, object] = {
        "option_strike_offset_pct": 5.0,
        "option_min_dte": 120,
        "option_max_dte": 365,
        "option_type": "call",
        "initial_cash": 5000.0,
        "id": 1,
        "strategy": "trend",
        "rotation_enabled": 0,
        "rotation_schedule": None,
        "rotation_active_index": 0,
        "rotation_last_at": None,
        "rotation_active_strategy": None,
        "rotation_mode": "time",
        "rotation_optimality_mode": "previous_period_best",
        "rotation_lookback_days": 180,
        "rotation_overlay_mode": "none",
    }
    values.update(overrides)
    return make_account_record(**values)


def make_feature_bundle(*, available: bool = True, **features: float) -> ExternalFeatureBundle:
    return ExternalFeatureBundle(features=dict(features), available=available)


def make_feature_fetcher(
    bundles_by_ticker: Mapping[str, Mapping[str, float]],
    *,
    available: bool = True,
) -> Callable[[str], ExternalFeatureBundle]:
    def _fetch(ticker: str) -> ExternalFeatureBundle:
        return make_feature_bundle(available=available, **dict(bundles_by_ticker.get(ticker, {})))

    return _fetch


def make_feature_fetchers(
    *,
    fetch_policy: Callable[[str], ExternalFeatureBundle] | None = None,
    fetch_news: Callable[[str], ExternalFeatureBundle] | None = None,
    fetch_social: Callable[[str], ExternalFeatureBundle] | None = None,
) -> FeatureFetcherSet:
    return FeatureFetcherSet(
        fetch_policy=fetch_policy or Mock(return_value=make_feature_bundle()),
        fetch_news=fetch_news or Mock(return_value=make_feature_bundle()),
        fetch_social=fetch_social or Mock(return_value=make_feature_bundle()),
    )


class FakeBroker:
    def __init__(self) -> None:
        self.disconnect = Mock()
        self.get_open_trades = Mock(return_value=[])
        self.place_order = Mock(side_effect=self._fill_order)

    @staticmethod
    def _fill_order(order):
        order.broker_order_id = "fake-broker-order"
        order.status = OrderStatus.FILLED
        order.filled_qty = order.qty
        order.avg_fill_price = order.price
        order.fills = []
        return order


def make_account_state(
    *,
    cash: float = 1000.0,
    positions: dict[str, float] | None = None,
    avg_cost: dict[str, float] | None = None,
    realized_pnl: float = 0.0,
) -> AccountState:
    return AccountState(
        cash=cash,
        positions=positions or {},
        avg_cost=avg_cost or {},
        realized_pnl=realized_pnl,
    )


__all__ = [
    "FakeBroker",
    "MARKET_CLOSED_TIME_ISO",
    "MARKET_OPEN_TIME_ISO",
    "make_account_state",
    "make_auto_trading_account",
    "make_feature_bundle",
    "make_feature_fetcher",
    "make_feature_fetchers",
]
