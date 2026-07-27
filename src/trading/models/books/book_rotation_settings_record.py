from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from common.coercion import row_expect_int, row_expect_str, row_float, row_int, row_str


@dataclass(frozen=True, slots=True)
class BookRotationSettingsRecord:
    """Persisted book_rotation_settings row materialized from the database.

    Settings only — rotation *state* lives in book_strategy_history (the
    open row) and rotation_decisions history. Rotation uses continuous
    evaluation gated by cooldown (ADR 014).

    The scheduling and policy fields are nullable: None means "use the
    BookRotationScheduleConfig / RotationPolicyConfig code default".
    """

    book_id: int
    rotation_enabled: int
    rotation_lookback_days: int | None
    rotation_schedule: str | None
    min_trades_in_window: int | None
    outperformance_threshold_bps: float | None
    cooldown_days: int | None
    risk_adjusted_return_weight: float | None
    stability_weight: float | None
    drawdown_penalty_weight: float | None
    regime_fit_weight: float | None
    created_at: str
    updated_at: str

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> BookRotationSettingsRecord:
        return cls(
            book_id=row_expect_int(values, "book_id"),
            rotation_enabled=row_expect_int(values, "rotation_enabled"),
            rotation_lookback_days=row_int(values, "rotation_lookback_days"),
            rotation_schedule=row_str(values, "rotation_schedule"),
            min_trades_in_window=row_int(values, "min_trades_in_window"),
            outperformance_threshold_bps=row_float(values, "outperformance_threshold_bps"),
            cooldown_days=row_int(values, "cooldown_days"),
            risk_adjusted_return_weight=row_float(values, "risk_adjusted_return_weight"),
            stability_weight=row_float(values, "stability_weight"),
            drawdown_penalty_weight=row_float(values, "drawdown_penalty_weight"),
            regime_fit_weight=row_float(values, "regime_fit_weight"),
            created_at=row_expect_str(values, "created_at"),
            updated_at=row_expect_str(values, "updated_at"),
        )
