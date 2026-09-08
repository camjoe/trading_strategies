from __future__ import annotations

from collections.abc import Callable, Mapping
from unittest.mock import Mock

from tests.support.account_records import make_account_record, make_book_record
from trading.domain.feature_provider import ExternalFeatureBundle, FeatureFetcherSet
from trading.models.accounts import AccountState
from trading.models.execution import BookTradeCandidate
from trading.models.orders import BrokerOrder, OrderStatus

MARKET_OPEN_TIME_ISO = "2026-03-14T14:00:00Z"
MARKET_CLOSED_TIME_ISO = "2026-03-15T15:00:00Z"


def make_auto_trading_account(**overrides: object):
    values: dict[str, object] = {
        "initial_cash": 5000.0,
        "id": 1,
        "strategy": "trend",
    }
    values.update(overrides)
    return make_account_record(**values)


def make_option_settings(**overrides: object):
    """A book carrying the option/leaps knobs (book columns since 0005)."""
    values: dict[str, object] = {
        "option_strike_offset_pct": 5.0,
        "option_min_dte": 120,
        "option_max_dte": 365,
        "option_type": "call",
    }
    values.update(overrides)
    return make_book_record(**values)


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
    """Fetchers shaped like the composition root's: policy supplied, the rest absent.

    News and social default to None because no registered strategy consumes them
    and `run_auto_trades` no longer wires them. Pass one explicitly to exercise a
    path that does.
    """
    return FeatureFetcherSet(
        fetch_policy=fetch_policy or Mock(return_value=make_feature_bundle()),
        fetch_news=fetch_news,
        fetch_social=fetch_social,
    )


class FakeBroker:
    def __init__(self) -> None:
        self.disconnect = Mock()
        self.get_open_trades = Mock(return_value=[])
        self.place_order = Mock(side_effect=self._fill_order)

    @staticmethod
    def _fill_order(order):
        placed = BrokerOrder.from_request(order)
        placed.broker_order_id = "fake-broker-order"
        placed.status = OrderStatus.FILLED
        placed.filled_qty = order.qty
        placed.avg_fill_price = order.price
        return placed


def make_book_trade_candidate(
    *,
    book_id: int,
    account_id: int = 1,
    symbol: str = "AAPL",
    side: str = "buy",
    qty: int = 1,
    requested_price: float = 100.0,
    strategy_name: str = "trend",
    forced_sell: str | None = None,
    delta_est: float | None = None,
    iv_est: float | None = None,
) -> BookTradeCandidate:
    return BookTradeCandidate(
        account_id=account_id,
        book_id=book_id,
        strategy_name=strategy_name,
        side=side,
        symbol=symbol,
        qty=qty,
        requested_price=requested_price,
        forced_sell=forced_sell,
        delta_est=delta_est,
        iv_est=iv_est,
    )


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
    "make_book_trade_candidate",
    "make_option_settings",
    "make_feature_bundle",
    "make_feature_fetcher",
    "make_feature_fetchers",
]
