from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass

from common.coercion import row_expect_float, row_expect_int, row_expect_str, row_float, row_int, row_str


@dataclass(frozen=True, slots=True)
class AccountRecord(Mapping[str, object]):
    """Persisted account row materialized from the database.

    The retired account rotation columns (rotation_*) were dropped in
    revision 0003 — rotation scheduling is book-owned and rotation state
    lives in book_strategy_assignments and rotation_decisions (ADR 014).
    """

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
    broker_type: str | None = None
    broker_host: str | None = None
    broker_port: int | None = None
    broker_client_id: int | None = None
    live_trading_enabled: int | None = None
    trade_universes: str | None = None

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> AccountRecord:
        return cls(
            id=row_expect_int(values, "id"),
            name=row_expect_str(values, "name"),
            account_kind=row_expect_str(values, "account_kind"),
            strategy=row_expect_str(values, "strategy"),
            initial_cash=row_expect_float(values, "initial_cash"),
            created_at=row_expect_str(values, "created_at"),
            benchmark_ticker=row_expect_str(values, "benchmark_ticker"),
            descriptive_name=row_expect_str(values, "descriptive_name"),
            goal_min_return_pct=row_float(values, "goal_min_return_pct"),
            goal_max_return_pct=row_float(values, "goal_max_return_pct"),
            goal_period=row_expect_str(values, "goal_period"),
            learning_enabled=row_expect_int(values, "learning_enabled"),
            risk_policy=row_expect_str(values, "risk_policy"),
            stop_loss_pct=row_float(values, "stop_loss_pct"),
            take_profit_pct=row_float(values, "take_profit_pct"),
            trade_size_pct=row_float(values, "trade_size_pct"),
            max_position_pct=row_float(values, "max_position_pct"),
            instrument_mode=row_expect_str(values, "instrument_mode"),
            option_strike_offset_pct=row_float(values, "option_strike_offset_pct"),
            option_min_dte=row_int(values, "option_min_dte"),
            option_max_dte=row_int(values, "option_max_dte"),
            option_type=row_str(values, "option_type"),
            target_delta_min=row_float(values, "target_delta_min"),
            target_delta_max=row_float(values, "target_delta_max"),
            max_premium_per_trade=row_float(values, "max_premium_per_trade"),
            max_contracts_per_trade=row_int(values, "max_contracts_per_trade"),
            iv_rank_min=row_float(values, "iv_rank_min"),
            iv_rank_max=row_float(values, "iv_rank_max"),
            roll_dte_threshold=row_int(values, "roll_dte_threshold"),
            profit_take_pct=row_float(values, "profit_take_pct"),
            max_loss_pct=row_float(values, "max_loss_pct"),
            broker_type=row_str(values, "broker_type"),
            broker_host=row_str(values, "broker_host"),
            broker_port=row_int(values, "broker_port"),
            broker_client_id=row_int(values, "broker_client_id"),
            live_trading_enabled=row_int(values, "live_trading_enabled"),
            trade_universes=row_str(values, "trade_universes"),
        )

    def __getitem__(self, key: str) -> object:
        if key not in self.__dataclass_fields__:
            raise KeyError(key)
        return getattr(self, key)

    def __iter__(self) -> Iterator[str]:
        return iter(self.__dataclass_fields__)

    def __len__(self) -> int:
        return len(self.__dataclass_fields__)
