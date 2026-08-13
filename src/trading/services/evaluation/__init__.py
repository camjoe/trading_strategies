"""Evaluation service package.

This package is the stable public evaluation surface.
"""

from __future__ import annotations

from trading.services.evaluation.presentation import backtest_freshness_display_parts
from trading.services.evaluation.queries import (
    fetch_strategy_evaluation,
    fetch_strategy_evaluation_for_account_row,
)

__all__ = [
    "backtest_freshness_display_parts",
    "fetch_strategy_evaluation",
    "fetch_strategy_evaluation_for_account_row",
]
