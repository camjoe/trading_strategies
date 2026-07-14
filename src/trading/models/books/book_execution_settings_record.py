from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from common.coercion import row_expect_int, row_expect_str, row_float, row_int


@dataclass(frozen=True, slots=True)
class BookExecutionSettingsRecord:
    """Persisted book_execution_settings row materialized from the database."""

    book_id: int
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
    def from_mapping(cls, values: Mapping[str, object]) -> BookExecutionSettingsRecord:
        return cls(
            book_id=row_expect_int(values, "book_id"),
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
