"""Sentinel strings shared across runtime jobs and UI status surfaces."""

from __future__ import annotations


DAILY_PAPER_TRADING_COMPLETE_SENTINEL = "COMPLETE: Daily paper trading run succeeded."
DAILY_SNAPSHOT_COMPLETE_SENTINEL = "COMPLETE: Daily snapshot run succeeded."
DAILY_BACKTEST_REFRESH_COMPLETE_SENTINEL = "COMPLETE: Daily backtest refresh succeeded."
WEEKLY_DB_BACKUP_COMPLETE_SENTINEL = "COMPLETE: Weekly database backup succeeded."

__all__ = [
    "DAILY_BACKTEST_REFRESH_COMPLETE_SENTINEL",
    "DAILY_PAPER_TRADING_COMPLETE_SENTINEL",
    "DAILY_SNAPSHOT_COMPLETE_SENTINEL",
    "WEEKLY_DB_BACKUP_COMPLETE_SENTINEL",
]
