from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Mapping, Sequence
from unittest.mock import Mock

from trading.features.base import ExternalFeatureBundle
from trading.models.account_state import AccountState
from trading.models.broker_order import OrderStatus
import trading.services.auto_trading.execution as execution_service
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


@dataclass
class RuntimeScenario:
    account: object
    state: object
    prepared_selection: object | Sequence[object] = ("buy", "AAPL", 1, 100.0, None, None)
    now_values: Sequence[str] = field(default_factory=lambda: [MARKET_OPEN_TIME_ISO])
    rotated_account: object | None = None
    broker: FakeBroker = field(default_factory=FakeBroker)
    trade_recorder: Mock = field(default_factory=Mock)
    window_open_fn: Callable[[str], bool] = field(default=lambda _now: True)
    forced_sell_ticker: str | None = None

    def install(self, monkeypatch, runtime_module) -> None:
        times = list(self.now_values)
        if not times:
            times = [MARKET_OPEN_TIME_ISO]

        def _next_time() -> str:
            if len(times) > 1:
                return times.pop(0)
            return times[0]

        selections = self.prepared_selection
        if isinstance(selections, Sequence) and selections and isinstance(selections[0], tuple):
            selection_values = list(selections)

            def _prepare_selection(*_args, **_kwargs):
                if not selection_values:
                    return None
                next_selection = selection_values.pop(0)
                return next_selection
        else:

            def _prepare_selection(*_args, **_kwargs):
                return selections

        monkeypatch.setattr(runtime_module, "get_account", Mock(return_value=self.account))
        monkeypatch.setattr(runtime_module, "_is_runtime_submission_window_open", self.window_open_fn)
        monkeypatch.setattr(runtime_module, "utc_now_iso", Mock(side_effect=_next_time))
        monkeypatch.setattr(
            runtime_module,
            "_rotate_runtime_account",
            Mock(return_value=self.rotated_account or self.account),
        )
        monkeypatch.setattr(
            execution_service,
            "refresh_account_state",
            Mock(return_value=self.state),
        )
        monkeypatch.setattr(
            execution_service,
            "prepare_trade_selection",
            Mock(side_effect=_prepare_selection),
        )
        monkeypatch.setattr(
            execution_service.auto_trader_policy,
            "choose_sell_ticker_by_risk",
            Mock(return_value=self.forced_sell_ticker),
        )
        monkeypatch.setattr(runtime_module, "_record_runtime_trade", self.trade_recorder)
        monkeypatch.setattr(runtime_module, "get_broker_for_account", Mock(return_value=self.broker))


__all__ = [
    "FakeBroker",
    "MARKET_CLOSED_TIME_ISO",
    "MARKET_OPEN_TIME_ISO",
    "RuntimeScenario",
    "make_account_state",
    "make_auto_trading_account",
    "make_feature_bundle",
    "make_feature_fetcher",
]
