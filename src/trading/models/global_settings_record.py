from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from common.coercion import row_expect_float, row_expect_int, row_int, row_str


@dataclass(frozen=True, slots=True)
class GlobalSettingsRecord:
    """Persisted global_settings singleton row materialized from the database."""

    runtime_max_trades_per_day: int | None
    runtime_max_trades_per_minute: int | None
    evaluation_backtest_trade_count_for_full_confidence: int
    evaluation_backtest_snapshot_count_for_full_confidence: int
    evaluation_paper_live_snapshot_count_for_full_confidence: int
    evaluation_backtest_trade_confidence_weight: float
    evaluation_backtest_snapshot_confidence_weight: float
    evaluation_backtest_evidence_weight: float
    evaluation_paper_live_evidence_weight: float
    promotion_min_research_backtest_trade_count: int
    promotion_min_research_backtest_snapshot_count: int
    promotion_min_research_backtest_return_pct: float
    promotion_min_research_max_drawdown_pct: float
    promotion_min_research_walk_forward_average_return_pct: float
    promotion_min_live_paper_snapshot_count: int
    promotion_min_live_overall_confidence: float
    updated_at: str | None

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> GlobalSettingsRecord:
        return cls(
            runtime_max_trades_per_day=row_int(values, "runtime_max_trades_per_day"),
            runtime_max_trades_per_minute=row_int(values, "runtime_max_trades_per_minute"),
            evaluation_backtest_trade_count_for_full_confidence=row_expect_int(
                values, "evaluation_backtest_trade_count_for_full_confidence"
            ),
            evaluation_backtest_snapshot_count_for_full_confidence=row_expect_int(
                values, "evaluation_backtest_snapshot_count_for_full_confidence"
            ),
            evaluation_paper_live_snapshot_count_for_full_confidence=row_expect_int(
                values, "evaluation_paper_live_snapshot_count_for_full_confidence"
            ),
            evaluation_backtest_trade_confidence_weight=row_expect_float(
                values, "evaluation_backtest_trade_confidence_weight"
            ),
            evaluation_backtest_snapshot_confidence_weight=row_expect_float(
                values, "evaluation_backtest_snapshot_confidence_weight"
            ),
            evaluation_backtest_evidence_weight=row_expect_float(values, "evaluation_backtest_evidence_weight"),
            evaluation_paper_live_evidence_weight=row_expect_float(values, "evaluation_paper_live_evidence_weight"),
            promotion_min_research_backtest_trade_count=row_expect_int(
                values, "promotion_min_research_backtest_trade_count"
            ),
            promotion_min_research_backtest_snapshot_count=row_expect_int(
                values, "promotion_min_research_backtest_snapshot_count"
            ),
            promotion_min_research_backtest_return_pct=row_expect_float(
                values, "promotion_min_research_backtest_return_pct"
            ),
            promotion_min_research_max_drawdown_pct=row_expect_float(
                values, "promotion_min_research_max_drawdown_pct"
            ),
            promotion_min_research_walk_forward_average_return_pct=row_expect_float(
                values, "promotion_min_research_walk_forward_average_return_pct"
            ),
            promotion_min_live_paper_snapshot_count=row_expect_int(values, "promotion_min_live_paper_snapshot_count"),
            promotion_min_live_overall_confidence=row_expect_float(values, "promotion_min_live_overall_confidence"),
            updated_at=row_str(values, "updated_at"),
        )
