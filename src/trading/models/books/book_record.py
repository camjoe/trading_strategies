from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from common.coercion import row_expect_float, row_expect_int, row_expect_str, row_float, row_int, row_str


@dataclass(frozen=True, slots=True)
class BookRecord:
    """Persisted books row materialized from the database."""

    id: int
    account_id: int
    name: str
    status: str
    is_default: int
    start_equity: float
    current_cash: float
    current_equity: float
    trade_universes: str | None
    goal_min_return_pct: float | None
    goal_max_return_pct: float | None
    goal_period: str | None
    # Execution settings are book columns since revision 0004 (roadmap A2).
    learning_enabled: int
    risk_policy: str
    stop_loss_pct: float | None
    take_profit_pct: float | None
    profit_take_pct: float | None
    max_loss_pct: float | None
    trade_size_pct: float | None
    max_position_pct: float | None
    max_trades_per_run: int | None
    instrument_mode: str
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
            trade_universes=row_str(values, "trade_universes"),
            goal_min_return_pct=row_float(values, "goal_min_return_pct"),
            goal_max_return_pct=row_float(values, "goal_max_return_pct"),
            goal_period=row_str(values, "goal_period"),
            learning_enabled=row_expect_int(values, "learning_enabled"),
            risk_policy=row_expect_str(values, "risk_policy"),
            stop_loss_pct=row_float(values, "stop_loss_pct"),
            take_profit_pct=row_float(values, "take_profit_pct"),
            profit_take_pct=row_float(values, "profit_take_pct"),
            max_loss_pct=row_float(values, "max_loss_pct"),
            trade_size_pct=row_float(values, "trade_size_pct"),
            max_position_pct=row_float(values, "max_position_pct"),
            max_trades_per_run=row_int(values, "max_trades_per_run"),
            instrument_mode=row_expect_str(values, "instrument_mode"),
            created_at=row_expect_str(values, "created_at"),
            updated_at=row_expect_str(values, "updated_at"),
        )
