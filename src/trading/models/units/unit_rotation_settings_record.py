from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from common.coercion import row_expect_int, row_expect_str, row_float, row_int, row_str


@dataclass(frozen=True, slots=True)
class UnitRotationSettingsRecord:
    """Persisted unit_rotation_settings row materialized from the database.

    Settings only — rotation *state* lives in unit_strategy_assignments (the open
    row) and rotation_decisions history (D4, 2026-07-03).
    """

    unit_id: int
    rotation_enabled: int
    rotation_mode: str | None
    rotation_optimality_mode: str | None
    rotation_interval_days: int | None
    rotation_interval_minutes: int | None
    rotation_lookback_days: int | None
    rotation_schedule: str | None
    regime_strategy_risk_on_id: int | None
    regime_strategy_neutral_id: int | None
    regime_strategy_risk_off_id: int | None
    overlay_mode: str | None
    overlay_min_tickers: int | None
    overlay_confidence_threshold: float | None
    overlay_watchlist: str | None
    created_at: str
    updated_at: str

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> UnitRotationSettingsRecord:
        return cls(
            unit_id=row_expect_int(values, "unit_id"),
            rotation_enabled=row_expect_int(values, "rotation_enabled"),
            rotation_mode=row_str(values, "rotation_mode"),
            rotation_optimality_mode=row_str(values, "rotation_optimality_mode"),
            rotation_interval_days=row_int(values, "rotation_interval_days"),
            rotation_interval_minutes=row_int(values, "rotation_interval_minutes"),
            rotation_lookback_days=row_int(values, "rotation_lookback_days"),
            rotation_schedule=row_str(values, "rotation_schedule"),
            regime_strategy_risk_on_id=row_int(values, "regime_strategy_risk_on_id"),
            regime_strategy_neutral_id=row_int(values, "regime_strategy_neutral_id"),
            regime_strategy_risk_off_id=row_int(values, "regime_strategy_risk_off_id"),
            overlay_mode=row_str(values, "overlay_mode"),
            overlay_min_tickers=row_int(values, "overlay_min_tickers"),
            overlay_confidence_threshold=row_float(values, "overlay_confidence_threshold"),
            overlay_watchlist=row_str(values, "overlay_watchlist"),
            created_at=row_expect_str(values, "created_at"),
            updated_at=row_expect_str(values, "updated_at"),
        )
