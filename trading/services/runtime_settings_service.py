from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from common.coercion import row_float, row_int
from trading.domain.evaluation_confidence import EvaluationConfidenceSettings
from trading.domain.promotion_policy import PromotionPolicySettings
from trading.repositories.global_settings_repository import fetch_global_settings_row


@dataclass(frozen=True)
class RuntimeThrottleSettings:
    max_trades_per_day: int | None = None
    max_trades_per_minute: int | None = None


def fetch_runtime_throttle_settings(conn: sqlite3.Connection) -> RuntimeThrottleSettings:
    if not hasattr(conn, "execute"):
        return RuntimeThrottleSettings()
    row = fetch_global_settings_row(conn)
    if row is None:
        return RuntimeThrottleSettings()
    return RuntimeThrottleSettings(
        max_trades_per_day=row_int(row, "runtime_max_trades_per_day"),
        max_trades_per_minute=row_int(row, "runtime_max_trades_per_minute"),
    )


def fetch_evaluation_confidence_settings(conn: sqlite3.Connection) -> EvaluationConfidenceSettings:
    defaults = EvaluationConfidenceSettings()
    if not hasattr(conn, "execute"):
        return defaults
    row = fetch_global_settings_row(conn)
    if row is None:
        return defaults
    backtest_trade_weight = row_float(row, "evaluation_backtest_trade_confidence_weight")
    backtest_snapshot_weight = row_float(row, "evaluation_backtest_snapshot_confidence_weight")
    backtest_evidence_weight = row_float(row, "evaluation_backtest_evidence_weight")
    paper_live_evidence_weight = row_float(row, "evaluation_paper_live_evidence_weight")
    return EvaluationConfidenceSettings(
        backtest_trade_count_for_full_confidence=(
            row_int(row, "evaluation_backtest_trade_count_for_full_confidence")
            or defaults.backtest_trade_count_for_full_confidence
        ),
        backtest_snapshot_count_for_full_confidence=(
            row_int(row, "evaluation_backtest_snapshot_count_for_full_confidence")
            or defaults.backtest_snapshot_count_for_full_confidence
        ),
        paper_live_snapshot_count_for_full_confidence=(
            row_int(row, "evaluation_paper_live_snapshot_count_for_full_confidence")
            or defaults.paper_live_snapshot_count_for_full_confidence
        ),
        backtest_trade_confidence_weight=(
            backtest_trade_weight
            if backtest_trade_weight is not None
            else defaults.backtest_trade_confidence_weight
        ),
        backtest_snapshot_confidence_weight=(
            backtest_snapshot_weight
            if backtest_snapshot_weight is not None
            else defaults.backtest_snapshot_confidence_weight
        ),
        backtest_evidence_weight=(
            backtest_evidence_weight
            if backtest_evidence_weight is not None
            else defaults.backtest_evidence_weight
        ),
        paper_live_evidence_weight=(
            paper_live_evidence_weight
            if paper_live_evidence_weight is not None
            else defaults.paper_live_evidence_weight
        ),
    )


def fetch_promotion_policy_settings(conn: sqlite3.Connection) -> PromotionPolicySettings:
    defaults = PromotionPolicySettings()
    if not hasattr(conn, "execute"):
        return defaults
    row = fetch_global_settings_row(conn)
    if row is None:
        return defaults
    min_research_backtest_return_pct = row_float(
        row, "promotion_min_research_backtest_return_pct"
    )
    min_research_max_drawdown_pct = row_float(
        row, "promotion_min_research_max_drawdown_pct"
    )
    min_research_walk_forward_average_return_pct = row_float(
        row, "promotion_min_research_walk_forward_average_return_pct"
    )
    min_live_overall_confidence = row_float(row, "promotion_min_live_overall_confidence")
    return PromotionPolicySettings(
        min_research_backtest_trade_count=(
            row_int(row, "promotion_min_research_backtest_trade_count")
            or defaults.min_research_backtest_trade_count
        ),
        min_research_backtest_snapshot_count=(
            row_int(row, "promotion_min_research_backtest_snapshot_count")
            or defaults.min_research_backtest_snapshot_count
        ),
        min_research_backtest_return_pct=(
            min_research_backtest_return_pct
            if min_research_backtest_return_pct is not None
            else defaults.min_research_backtest_return_pct
        ),
        min_research_max_drawdown_pct=(
            min_research_max_drawdown_pct
            if min_research_max_drawdown_pct is not None
            else defaults.min_research_max_drawdown_pct
        ),
        min_research_walk_forward_average_return_pct=(
            min_research_walk_forward_average_return_pct
            if min_research_walk_forward_average_return_pct is not None
            else defaults.min_research_walk_forward_average_return_pct
        ),
        min_live_paper_snapshot_count=(
            row_int(row, "promotion_min_live_paper_snapshot_count")
            or defaults.min_live_paper_snapshot_count
        ),
        min_live_overall_confidence=(
            min_live_overall_confidence
            if min_live_overall_confidence is not None
            else defaults.min_live_overall_confidence
        ),
    )
