"""Operational settings mutations for operational-settings consumers.

Owns caller-facing validation and write orchestration for persisted operational
settings beneath the stable ``trading.services.operational_settings`` package
surface.
"""

from __future__ import annotations

import math
import sqlite3

from trading.repositories.global_settings import GlobalSettingsRepository

# Evaluation confidence weights must remain normalized so blended confidence
# calculations continue to behave like weighted averages.
EXPECTED_WEIGHT_SUM = 1.0

# Allow a tiny tolerance for float input while still rejecting materially
# invalid settings such as 0.8 + 0.8.
WEIGHT_SUM_TOLERANCE = 1e-9


def _validate_weight_sum(
    *,
    first_name: str,
    first_value: float,
    second_name: str,
    second_value: float,
) -> None:
    total = first_value + second_value
    has_expected_weight_sum = math.isclose(total, EXPECTED_WEIGHT_SUM, rel_tol=0.0, abs_tol=WEIGHT_SUM_TOLERANCE)
    if has_expected_weight_sum:
        return
    raise ValueError(f"{first_name} + {second_name} must equal {EXPECTED_WEIGHT_SUM:.1f}; got {total:.6f}.")


def set_runtime_throttle_settings(
    conn: sqlite3.Connection,
    *,
    runtime_max_trades_per_day: int | None,
    runtime_max_trades_per_minute: int | None,
    updated_at: str,
) -> None:
    GlobalSettingsRepository(conn).upsert_throttle_settings(
        runtime_max_trades_per_day=runtime_max_trades_per_day,
        runtime_max_trades_per_minute=runtime_max_trades_per_minute,
        updated_at=updated_at,
    )


def set_evaluation_confidence_settings(
    conn: sqlite3.Connection,
    *,
    backtest_trade_count_for_full_confidence: int,
    backtest_snapshot_count_for_full_confidence: int,
    paper_live_snapshot_count_for_full_confidence: int,
    backtest_trade_confidence_weight: float,
    backtest_snapshot_confidence_weight: float,
    backtest_evidence_weight: float,
    paper_live_evidence_weight: float,
    updated_at: str,
) -> None:
    _validate_weight_sum(
        first_name="backtest_trade_confidence_weight",
        first_value=backtest_trade_confidence_weight,
        second_name="backtest_snapshot_confidence_weight",
        second_value=backtest_snapshot_confidence_weight,
    )
    _validate_weight_sum(
        first_name="backtest_evidence_weight",
        first_value=backtest_evidence_weight,
        second_name="paper_live_evidence_weight",
        second_value=paper_live_evidence_weight,
    )
    GlobalSettingsRepository(conn).upsert_evaluation_settings(
        backtest_trade_count_for_full_confidence=backtest_trade_count_for_full_confidence,
        backtest_snapshot_count_for_full_confidence=backtest_snapshot_count_for_full_confidence,
        paper_live_snapshot_count_for_full_confidence=paper_live_snapshot_count_for_full_confidence,
        backtest_trade_confidence_weight=backtest_trade_confidence_weight,
        backtest_snapshot_confidence_weight=backtest_snapshot_confidence_weight,
        backtest_evidence_weight=backtest_evidence_weight,
        paper_live_evidence_weight=paper_live_evidence_weight,
        updated_at=updated_at,
    )


def set_promotion_policy_settings(
    conn: sqlite3.Connection,
    *,
    min_research_backtest_trade_count: int,
    min_research_backtest_snapshot_count: int,
    min_research_backtest_return_pct: float,
    min_research_max_drawdown_pct: float,
    min_research_walk_forward_average_return_pct: float,
    min_live_paper_snapshot_count: int,
    min_live_overall_confidence: float,
    updated_at: str,
) -> None:
    GlobalSettingsRepository(conn).upsert_promotion_settings(
        min_research_backtest_trade_count=min_research_backtest_trade_count,
        min_research_backtest_snapshot_count=min_research_backtest_snapshot_count,
        min_research_backtest_return_pct=min_research_backtest_return_pct,
        min_research_max_drawdown_pct=min_research_max_drawdown_pct,
        min_research_walk_forward_average_return_pct=min_research_walk_forward_average_return_pct,
        min_live_paper_snapshot_count=min_live_paper_snapshot_count,
        min_live_overall_confidence=min_live_overall_confidence,
        updated_at=updated_at,
    )


__all__ = [
    "EXPECTED_WEIGHT_SUM",
    "WEIGHT_SUM_TOLERANCE",
    "set_evaluation_confidence_settings",
    "set_promotion_policy_settings",
    "set_runtime_throttle_settings",
]
