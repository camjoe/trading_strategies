from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass

from common.coercion import coerce_float, coerce_int, coerce_str, expect_float, expect_int, expect_str


@dataclass(frozen=True, slots=True)
class AccountRecord(Mapping[str, object]):
    """Persisted account row materialized from the database."""

    id: int
    name: str
    account_kind: str
    strategy: str
    initial_cash: float
    created_at: str
    benchmark_ticker: str
    descriptive_name: str
    goal_min_return_pct: float | None
    goal_max_return_pct: float | None
    goal_period: str
    learning_enabled: int
    risk_policy: str
    stop_loss_pct: float | None
    take_profit_pct: float | None
    trade_size_pct: float | None
    max_position_pct: float | None
    instrument_mode: str
    option_strike_offset_pct: float | None
    option_min_dte: int | None
    option_max_dte: int | None
    option_type: str | None
    target_delta_min: float | None
    target_delta_max: float | None
    max_premium_per_trade: float | None
    max_contracts_per_trade: int | None
    iv_rank_min: float | None
    iv_rank_max: float | None
    roll_dte_threshold: int | None
    profit_take_pct: float | None
    max_loss_pct: float | None
    rotation_enabled: int | None = None
    rotation_mode: str | None = None
    rotation_optimality_mode: str | None = None
    rotation_interval_days: int | None = None
    rotation_interval_minutes: int | None = None
    rotation_lookback_days: int | None = None
    rotation_schedule: str | None = None
    rotation_regime_strategy_risk_on: str | None = None
    rotation_regime_strategy_neutral: str | None = None
    rotation_regime_strategy_risk_off: str | None = None
    rotation_overlay_mode: str | None = None
    rotation_overlay_min_tickers: int | None = None
    rotation_overlay_confidence_threshold: float | None = None
    rotation_overlay_watchlist: str | None = None
    rotation_active_index: int | None = None
    rotation_last_at: str | None = None
    rotation_active_strategy: str | None = None
    broker_type: str | None = None
    broker_host: str | None = None
    broker_port: int | None = None
    broker_client_id: int | None = None
    live_trading_enabled: int | None = None
    trade_universes: str | None = None

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> AccountRecord:
        return cls(
            id=expect_int(values.get("id"), "id"),
            name=expect_str(values.get("name"), "name"),
            account_kind=expect_str(values.get("account_kind"), "account_kind"),
            strategy=expect_str(values.get("strategy"), "strategy"),
            initial_cash=expect_float(values.get("initial_cash"), "initial_cash"),
            created_at=expect_str(values.get("created_at"), "created_at"),
            benchmark_ticker=expect_str(values.get("benchmark_ticker"), "benchmark_ticker"),
            descriptive_name=expect_str(values.get("descriptive_name"), "descriptive_name"),
            goal_min_return_pct=coerce_float(values.get("goal_min_return_pct")),
            goal_max_return_pct=coerce_float(values.get("goal_max_return_pct")),
            goal_period=expect_str(values.get("goal_period"), "goal_period"),
            learning_enabled=expect_int(values.get("learning_enabled"), "learning_enabled"),
            risk_policy=expect_str(values.get("risk_policy"), "risk_policy"),
            stop_loss_pct=coerce_float(values.get("stop_loss_pct")),
            take_profit_pct=coerce_float(values.get("take_profit_pct")),
            trade_size_pct=coerce_float(values.get("trade_size_pct")),
            max_position_pct=coerce_float(values.get("max_position_pct")),
            instrument_mode=expect_str(values.get("instrument_mode"), "instrument_mode"),
            option_strike_offset_pct=coerce_float(values.get("option_strike_offset_pct")),
            option_min_dte=coerce_int(values.get("option_min_dte")),
            option_max_dte=coerce_int(values.get("option_max_dte")),
            option_type=coerce_str(values.get("option_type")),
            target_delta_min=coerce_float(values.get("target_delta_min")),
            target_delta_max=coerce_float(values.get("target_delta_max")),
            max_premium_per_trade=coerce_float(values.get("max_premium_per_trade")),
            max_contracts_per_trade=coerce_int(values.get("max_contracts_per_trade")),
            iv_rank_min=coerce_float(values.get("iv_rank_min")),
            iv_rank_max=coerce_float(values.get("iv_rank_max")),
            roll_dte_threshold=coerce_int(values.get("roll_dte_threshold")),
            profit_take_pct=coerce_float(values.get("profit_take_pct")),
            max_loss_pct=coerce_float(values.get("max_loss_pct")),
            rotation_enabled=coerce_int(values.get("rotation_enabled")),
            rotation_mode=coerce_str(values.get("rotation_mode")),
            rotation_optimality_mode=coerce_str(values.get("rotation_optimality_mode")),
            rotation_interval_days=coerce_int(values.get("rotation_interval_days")),
            rotation_interval_minutes=coerce_int(values.get("rotation_interval_minutes")),
            rotation_lookback_days=coerce_int(values.get("rotation_lookback_days")),
            rotation_schedule=coerce_str(values.get("rotation_schedule")),
            rotation_regime_strategy_risk_on=coerce_str(values.get("rotation_regime_strategy_risk_on")),
            rotation_regime_strategy_neutral=coerce_str(values.get("rotation_regime_strategy_neutral")),
            rotation_regime_strategy_risk_off=coerce_str(values.get("rotation_regime_strategy_risk_off")),
            rotation_overlay_mode=coerce_str(values.get("rotation_overlay_mode")),
            rotation_overlay_min_tickers=coerce_int(values.get("rotation_overlay_min_tickers")),
            rotation_overlay_confidence_threshold=coerce_float(values.get("rotation_overlay_confidence_threshold")),
            rotation_overlay_watchlist=coerce_str(values.get("rotation_overlay_watchlist")),
            rotation_active_index=coerce_int(values.get("rotation_active_index")),
            rotation_last_at=coerce_str(values.get("rotation_last_at")),
            rotation_active_strategy=coerce_str(values.get("rotation_active_strategy")),
            broker_type=coerce_str(values.get("broker_type")),
            broker_host=coerce_str(values.get("broker_host")),
            broker_port=coerce_int(values.get("broker_port")),
            broker_client_id=coerce_int(values.get("broker_client_id")),
            live_trading_enabled=coerce_int(values.get("live_trading_enabled")),
            trade_universes=coerce_str(values.get("trade_universes")),
        )

    def __getitem__(self, key: str) -> object:
        if key not in self.__dataclass_fields__:
            raise KeyError(key)
        return getattr(self, key)

    def __iter__(self) -> Iterator[str]:
        return iter(self.__dataclass_fields__)

    def __len__(self) -> int:
        return len(self.__dataclass_fields__)
