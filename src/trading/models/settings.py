"""Global-settings data contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from common.coercion import row_expect_int, row_expect_str, row_float, row_int, row_str
from common.json_columns import row_json_object

# Which global_settings upsert wrote a global_settings_change_events row.
GLOBAL_SETTINGS_GROUP_THROTTLE = "throttle"
GLOBAL_SETTINGS_GROUP_EVALUATION = "evaluation"
GLOBAL_SETTINGS_GROUP_PROMOTION = "promotion"


@dataclass(frozen=True, slots=True)
class GlobalSettingsRecord:
    """Persisted nullable global-settings overrides materialized from the database."""

    runtime_max_trades_per_day: int | None
    runtime_max_trades_per_minute: int | None
    evaluation_backtest_trade_count_for_full_confidence: int | None
    evaluation_backtest_snapshot_count_for_full_confidence: int | None
    evaluation_paper_live_snapshot_count_for_full_confidence: int | None
    evaluation_backtest_trade_confidence_weight: float | None
    evaluation_backtest_snapshot_confidence_weight: float | None
    evaluation_backtest_evidence_weight: float | None
    evaluation_paper_live_evidence_weight: float | None
    promotion_min_research_backtest_trade_count: int | None
    promotion_min_research_backtest_snapshot_count: int | None
    promotion_min_research_backtest_return_pct: float | None
    promotion_min_research_max_drawdown_pct: float | None
    promotion_min_research_walk_forward_average_return_pct: float | None
    promotion_min_live_paper_snapshot_count: int | None
    promotion_min_live_overall_confidence: float | None
    updated_at: str | None

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> GlobalSettingsRecord:
        return cls(
            runtime_max_trades_per_day=row_int(values, "runtime_max_trades_per_day"),
            runtime_max_trades_per_minute=row_int(values, "runtime_max_trades_per_minute"),
            evaluation_backtest_trade_count_for_full_confidence=row_int(
                values, "evaluation_backtest_trade_count_for_full_confidence"
            ),
            evaluation_backtest_snapshot_count_for_full_confidence=row_int(
                values, "evaluation_backtest_snapshot_count_for_full_confidence"
            ),
            evaluation_paper_live_snapshot_count_for_full_confidence=row_int(
                values, "evaluation_paper_live_snapshot_count_for_full_confidence"
            ),
            evaluation_backtest_trade_confidence_weight=row_float(
                values, "evaluation_backtest_trade_confidence_weight"
            ),
            evaluation_backtest_snapshot_confidence_weight=row_float(
                values, "evaluation_backtest_snapshot_confidence_weight"
            ),
            evaluation_backtest_evidence_weight=row_float(values, "evaluation_backtest_evidence_weight"),
            evaluation_paper_live_evidence_weight=row_float(values, "evaluation_paper_live_evidence_weight"),
            promotion_min_research_backtest_trade_count=row_int(values, "promotion_min_research_backtest_trade_count"),
            promotion_min_research_backtest_snapshot_count=row_int(
                values, "promotion_min_research_backtest_snapshot_count"
            ),
            promotion_min_research_backtest_return_pct=row_float(values, "promotion_min_research_backtest_return_pct"),
            promotion_min_research_max_drawdown_pct=row_float(values, "promotion_min_research_max_drawdown_pct"),
            promotion_min_research_walk_forward_average_return_pct=row_float(
                values, "promotion_min_research_walk_forward_average_return_pct"
            ),
            promotion_min_live_paper_snapshot_count=row_int(values, "promotion_min_live_paper_snapshot_count"),
            promotion_min_live_overall_confidence=row_float(values, "promotion_min_live_overall_confidence"),
            updated_at=row_str(values, "updated_at"),
        )


@dataclass(frozen=True, slots=True)
class GlobalSettingsChangeEvent:
    """One audited edit to a global_settings field: prior and new value, when.

    ``changed_fields`` holds only fields whose value actually changed, keyed by
    field name to ``{"old": ..., "new": ...}``.
    """

    id: int
    settings_group: str
    changed_fields: dict[str, dict[str, object]]
    created_at: str

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> GlobalSettingsChangeEvent:
        return cls(
            id=row_expect_int(values, "id"),
            settings_group=row_expect_str(values, "settings_group"),
            changed_fields=row_json_object(values, "changed_fields"),
            created_at=row_expect_str(values, "created_at"),
        )
