"""Reporting service package.

This package is the operator-facing presentation surface: it formats and prints
account reports, comparisons, snapshots, and the cross-account concentration and
exposure rollups. The read-only computation it consumes lives in
``trading.services.analysis`` (portfolio/benchmark payloads),
``trading.services.evaluation`` (strategy evidence), and
``trading.domain.portfolio_math`` (pure return math).
"""

from __future__ import annotations

from trading.services.reporting.concentration import show_portfolio_concentration
from trading.services.reporting.exposure import show_portfolio_exposure
from trading.services.reporting.presentation import (
    account_report,
    compare_strategies,
    show_snapshots,
    snapshot_account,
)

__all__ = [
    "account_report",
    "compare_strategies",
    "show_portfolio_concentration",
    "show_portfolio_exposure",
    "show_snapshots",
    "snapshot_account",
]
