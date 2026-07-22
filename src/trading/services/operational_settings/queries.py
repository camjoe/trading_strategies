"""Operational settings queries for operational-settings consumers.

Owns caller-facing reads of persisted operational settings beneath the stable
``trading.services.operational_settings`` package surface.
"""

from __future__ import annotations

import sqlite3

from trading.domain.evaluation_confidence import EvaluationConfidenceSettings
from trading.domain.promotion_policy import PromotionPolicySettings
from trading.repositories.global_settings import GlobalSettingsRepository
from trading.services.operational_settings.models import RuntimeThrottleSettings


def _override[T](value: T | None, default: T) -> T:
    """Return an explicit database override or its code-owned default."""
    return default if value is None else value


def fetch_runtime_throttle_settings(conn: sqlite3.Connection) -> RuntimeThrottleSettings:
    if not hasattr(conn, "execute"):
        return RuntimeThrottleSettings()
    record = GlobalSettingsRepository(conn).fetch()
    if record is None:
        return RuntimeThrottleSettings()
    return RuntimeThrottleSettings(
        max_trades_per_day=record.runtime_max_trades_per_day,
        max_trades_per_minute=record.runtime_max_trades_per_minute,
    )


def fetch_evaluation_confidence_settings(conn: sqlite3.Connection) -> EvaluationConfidenceSettings:
    defaults = EvaluationConfidenceSettings()
    if not hasattr(conn, "execute"):
        return defaults
    record = GlobalSettingsRepository(conn).fetch()
    if record is None:
        return defaults
    return EvaluationConfidenceSettings(
        backtest_trade_count_for_full_confidence=_override(
            record.evaluation_backtest_trade_count_for_full_confidence,
            defaults.backtest_trade_count_for_full_confidence,
        ),
        backtest_snapshot_count_for_full_confidence=_override(
            record.evaluation_backtest_snapshot_count_for_full_confidence,
            defaults.backtest_snapshot_count_for_full_confidence,
        ),
        paper_live_snapshot_count_for_full_confidence=_override(
            record.evaluation_paper_live_snapshot_count_for_full_confidence,
            defaults.paper_live_snapshot_count_for_full_confidence,
        ),
        backtest_trade_confidence_weight=_override(
            record.evaluation_backtest_trade_confidence_weight,
            defaults.backtest_trade_confidence_weight,
        ),
        backtest_snapshot_confidence_weight=_override(
            record.evaluation_backtest_snapshot_confidence_weight,
            defaults.backtest_snapshot_confidence_weight,
        ),
        backtest_evidence_weight=_override(
            record.evaluation_backtest_evidence_weight,
            defaults.backtest_evidence_weight,
        ),
        paper_live_evidence_weight=_override(
            record.evaluation_paper_live_evidence_weight,
            defaults.paper_live_evidence_weight,
        ),
    )


def fetch_promotion_policy_settings(conn: sqlite3.Connection) -> PromotionPolicySettings:
    defaults = PromotionPolicySettings()
    if not hasattr(conn, "execute"):
        return defaults
    record = GlobalSettingsRepository(conn).fetch()
    if record is None:
        return defaults
    return PromotionPolicySettings(
        min_research_backtest_trade_count=_override(
            record.promotion_min_research_backtest_trade_count,
            defaults.min_research_backtest_trade_count,
        ),
        min_research_backtest_snapshot_count=_override(
            record.promotion_min_research_backtest_snapshot_count,
            defaults.min_research_backtest_snapshot_count,
        ),
        min_research_backtest_return_pct=_override(
            record.promotion_min_research_backtest_return_pct,
            defaults.min_research_backtest_return_pct,
        ),
        min_research_max_drawdown_pct=_override(
            record.promotion_min_research_max_drawdown_pct,
            defaults.min_research_max_drawdown_pct,
        ),
        min_research_walk_forward_average_return_pct=_override(
            record.promotion_min_research_walk_forward_average_return_pct,
            defaults.min_research_walk_forward_average_return_pct,
        ),
        min_live_paper_snapshot_count=_override(
            record.promotion_min_live_paper_snapshot_count,
            defaults.min_live_paper_snapshot_count,
        ),
        min_live_overall_confidence=_override(
            record.promotion_min_live_overall_confidence,
            defaults.min_live_overall_confidence,
        ),
    )


__all__ = [
    "fetch_evaluation_confidence_settings",
    "fetch_promotion_policy_settings",
    "fetch_runtime_throttle_settings",
]
