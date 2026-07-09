from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from common.coercion import row_expect_int, row_expect_str, row_float, row_int, row_str


@dataclass(frozen=True, slots=True)
class BookRotationSettingsRecord:
    """Persisted book_rotation_settings row materialized from the database.

    Settings only — rotation *state* lives in book_strategy_assignments (the open
    row) and rotation_decisions history (D4, 2026-07-03). The dead mode/optimality/
    regime/overlay columns are retained on the table (append-only) but no longer
    materialized here (2b-7).

    The rotation-policy fields (P7 step 4) are nullable: None means "use the
    RotationPolicyConfig code default".
    """

    book_id: int
    rotation_enabled: int
    rotation_interval_days: int | None
    rotation_interval_minutes: int | None
    rotation_lookback_days: int | None
    rotation_schedule: str | None
    min_trades_in_window: int | None
    outperformance_threshold_bps: float | None
    cooldown_days: int | None
    risk_adjusted_return_weight: float | None
    stability_weight: float | None
    drawdown_penalty_weight: float | None
    cost_penalty_weight: float | None
    regime_fit_weight: float | None
    created_at: str
    updated_at: str

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> BookRotationSettingsRecord:
        return cls(
            book_id=row_expect_int(values, "book_id"),
            rotation_enabled=row_expect_int(values, "rotation_enabled"),
            rotation_interval_days=row_int(values, "rotation_interval_days"),
            rotation_interval_minutes=row_int(values, "rotation_interval_minutes"),
            rotation_lookback_days=row_int(values, "rotation_lookback_days"),
            rotation_schedule=row_str(values, "rotation_schedule"),
            min_trades_in_window=row_int(values, "min_trades_in_window"),
            outperformance_threshold_bps=row_float(values, "outperformance_threshold_bps"),
            cooldown_days=row_int(values, "cooldown_days"),
            risk_adjusted_return_weight=row_float(values, "risk_adjusted_return_weight"),
            stability_weight=row_float(values, "stability_weight"),
            drawdown_penalty_weight=row_float(values, "drawdown_penalty_weight"),
            cost_penalty_weight=row_float(values, "cost_penalty_weight"),
            regime_fit_weight=row_float(values, "regime_fit_weight"),
            created_at=row_expect_str(values, "created_at"),
            updated_at=row_expect_str(values, "updated_at"),
        )
