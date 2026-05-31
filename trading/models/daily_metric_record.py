from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from common.coercion import row_expect_int, row_expect_str, row_float, row_int, row_str


@dataclass(frozen=True, slots=True)
class DailyMetricRecord:
    """Persisted daily_metrics row materialized from the database."""

    id: int
    account_id: int
    sleeve_id: int | None
    metric_date: str
    return_pct: float | None
    drawdown_pct: float | None
    turnover_pct: float | None
    slippage_bps: float | None
    hit_rate: float | None
    expectancy: float | None
    risk_adjusted_score: float | None
    trade_count: int | None
    fees_total: float | None
    created_at: str
    updated_at: str

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> DailyMetricRecord:
        return cls(
            id=row_expect_int(values, "id"),
            account_id=row_expect_int(values, "account_id"),
            sleeve_id=row_int(values, "sleeve_id"),
            metric_date=row_expect_str(values, "metric_date"),
            return_pct=row_float(values, "return_pct"),
            drawdown_pct=row_float(values, "drawdown_pct"),
            turnover_pct=row_float(values, "turnover_pct"),
            slippage_bps=row_float(values, "slippage_bps"),
            hit_rate=row_float(values, "hit_rate"),
            expectancy=row_float(values, "expectancy"),
            risk_adjusted_score=row_float(values, "risk_adjusted_score"),
            trade_count=row_int(values, "trade_count"),
            fees_total=row_float(values, "fees_total"),
            created_at=row_expect_str(values, "created_at"),
            updated_at=row_expect_str(values, "updated_at"),
        )
