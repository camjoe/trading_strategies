"""Shared runtime job status constants used across interfaces and services."""

from __future__ import annotations


DAILY_PAPER_TRADING_COMPLETE_SENTINEL = "COMPLETE: Daily paper trading run succeeded."
DAILY_SNAPSHOT_COMPLETE_SENTINEL = "COMPLETE: Daily snapshot run succeeded."
SCHEDULED_BACKTEST_REFRESH_COMPLETE_SENTINEL = "COMPLETE: Scheduled backtest refresh succeeded."
WEEKLY_DB_BACKUP_COMPLETE_SENTINEL = "COMPLETE: Weekly database backup succeeded."
