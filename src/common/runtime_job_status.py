"""Sentinel strings shared across runtime jobs and UI status surfaces."""

from __future__ import annotations


# Top-level `status` vocabulary written to daily paper-trading run artifacts
# (local/exports/daily_paper_trading/*.json) and read by the burn-in readiness scan.
# Distinct from the per-step statuses ("ok" | "skipped" | "failed") inside step_results.
DAILY_RUN_STATUS_SUCCESS = "success"
DAILY_RUN_STATUS_FAILED = "failed"

BURN_IN_STATUS_COMPLETE_SENTINEL = "COMPLETE: Burn-in status check succeeded."
DAILY_PAPER_TRADING_COMPLETE_SENTINEL = "COMPLETE: Daily paper trading run succeeded."
DAILY_SNAPSHOT_COMPLETE_SENTINEL = "COMPLETE: Daily snapshot run succeeded."
DAILY_BACKTEST_REFRESH_COMPLETE_SENTINEL = "COMPLETE: Daily backtest refresh succeeded."
DAILY_CHALLENGER_SHADOW_EVAL_COMPLETE_SENTINEL = "COMPLETE: Daily challenger shadow evaluation succeeded."
WEEKLY_DB_BACKUP_COMPLETE_SENTINEL = "COMPLETE: Weekly database backup succeeded."

WEEKLY_GOVERNANCE_W1_LEADERBOARD_COMPLETE_SENTINEL = "COMPLETE: Weekly governance W1 strategy leaderboard succeeded."
WEEKLY_GOVERNANCE_W2_PROMOTION_REVIEW_COMPLETE_SENTINEL = "COMPLETE: Weekly governance W2 promotion review succeeded."
WEEKLY_GOVERNANCE_W3_ALLOCATION_REVIEW_COMPLETE_SENTINEL = (
    "COMPLETE: Weekly governance W3 allocation review succeeded."
)
MONTHLY_GOVERNANCE_M1_RISK_REBASELINE_COMPLETE_SENTINEL = "COMPLETE: Monthly governance M1 risk rebaseline succeeded."
MONTHLY_GOVERNANCE_M2_PARAMETER_GOVERNANCE_COMPLETE_SENTINEL = (
    "COMPLETE: Monthly governance M2 parameter governance succeeded."
)
MONTHLY_GOVERNANCE_M3_PERFORMANCE_AUDIT_COMPLETE_SENTINEL = (
    "COMPLETE: Monthly governance M3 performance audit succeeded."
)

__all__ = [
    "DAILY_RUN_STATUS_SUCCESS",
    "DAILY_RUN_STATUS_FAILED",
    "BURN_IN_STATUS_COMPLETE_SENTINEL",
    "DAILY_BACKTEST_REFRESH_COMPLETE_SENTINEL",
    "DAILY_CHALLENGER_SHADOW_EVAL_COMPLETE_SENTINEL",
    "DAILY_PAPER_TRADING_COMPLETE_SENTINEL",
    "DAILY_SNAPSHOT_COMPLETE_SENTINEL",
    "WEEKLY_DB_BACKUP_COMPLETE_SENTINEL",
    "WEEKLY_GOVERNANCE_W1_LEADERBOARD_COMPLETE_SENTINEL",
    "WEEKLY_GOVERNANCE_W2_PROMOTION_REVIEW_COMPLETE_SENTINEL",
    "WEEKLY_GOVERNANCE_W3_ALLOCATION_REVIEW_COMPLETE_SENTINEL",
    "MONTHLY_GOVERNANCE_M1_RISK_REBASELINE_COMPLETE_SENTINEL",
    "MONTHLY_GOVERNANCE_M2_PARAMETER_GOVERNANCE_COMPLETE_SENTINEL",
    "MONTHLY_GOVERNANCE_M3_PERFORMANCE_AUDIT_COMPLETE_SENTINEL",
]
