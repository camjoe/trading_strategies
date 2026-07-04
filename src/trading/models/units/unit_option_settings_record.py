from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from common.coercion import row_expect_int, row_expect_str, row_float, row_int, row_str


@dataclass(frozen=True, slots=True)
class UnitOptionSettingsRecord:
    """Persisted unit_option_settings row materialized from the database."""

    unit_id: int
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
    def from_mapping(cls, values: Mapping[str, object]) -> UnitOptionSettingsRecord:
        return cls(
            unit_id=row_expect_int(values, "unit_id"),
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
