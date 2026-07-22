from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass

from common.coercion import row_expect_float, row_expect_int, row_expect_str, row_float, row_int, row_str


@dataclass(frozen=True, slots=True)
class BookRecord(Mapping[str, object]):
    """Persisted books row materialized from the database.

    Mapping access mirrors AccountRecord so domain policy functions that take
    a settings mapping (option/leaps knobs are book columns since revision
    0005) accept a book directly.
    """

    id: int
    account_id: int
    name: str
    status: str
    is_default: int
    start_equity: float
    current_cash: float
    current_equity: float
    # NOT NULL since revision 0008 — books are always explicitly set.
    trade_universes: str
    goal_min_return_pct: float | None
    goal_max_return_pct: float | None
    goal_period: str | None
    # Execution settings are book columns since revision 0004 (roadmap A2).
    learning_enabled: int
    risk_policy: str
    stop_loss_pct: float | None
    take_profit_pct: float | None
    option_profit_take_pct: float | None
    option_max_loss_pct: float | None
    trade_size_pct: float | None
    max_position_pct: float | None
    max_trades_per_run: int | None
    instrument_mode: str
    # Option/leaps settings are book columns since revision 0005 (roadmap A3).
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
    created_at: str
    updated_at: str

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> BookRecord:
        return cls(
            id=row_expect_int(values, "id"),
            account_id=row_expect_int(values, "account_id"),
            name=row_expect_str(values, "name"),
            status=row_expect_str(values, "status"),
            is_default=row_expect_int(values, "is_default"),
            start_equity=row_expect_float(values, "start_equity"),
            current_cash=row_expect_float(values, "current_cash"),
            current_equity=row_expect_float(values, "current_equity"),
            trade_universes=row_expect_str(values, "trade_universes"),
            goal_min_return_pct=row_float(values, "goal_min_return_pct"),
            goal_max_return_pct=row_float(values, "goal_max_return_pct"),
            goal_period=row_str(values, "goal_period"),
            learning_enabled=row_expect_int(values, "learning_enabled"),
            risk_policy=row_expect_str(values, "risk_policy"),
            stop_loss_pct=row_float(values, "stop_loss_pct"),
            take_profit_pct=row_float(values, "take_profit_pct"),
            option_profit_take_pct=row_float(values, "option_profit_take_pct"),
            option_max_loss_pct=row_float(values, "option_max_loss_pct"),
            trade_size_pct=row_float(values, "trade_size_pct"),
            max_position_pct=row_float(values, "max_position_pct"),
            max_trades_per_run=row_int(values, "max_trades_per_run"),
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
            created_at=row_expect_str(values, "created_at"),
            updated_at=row_expect_str(values, "updated_at"),
        )

    def __getitem__(self, key: str) -> object:
        if key not in self.__dataclass_fields__:
            raise KeyError(key)
        return getattr(self, key)

    def __iter__(self) -> Iterator[str]:
        return iter(self.__dataclass_fields__)

    def __len__(self) -> int:
        return len(self.__dataclass_fields__)
