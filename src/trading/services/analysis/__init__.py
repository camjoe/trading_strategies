"""Analysis service package.

This package is the stable public surface for read-only analytical queries:
per-account analysis, sleeve performance windows, and portfolio risk snapshots.
Concrete logic lives in focused modules beneath this package root.
"""

from __future__ import annotations

from trading.services.analysis.performance import fetch_sleeve_performance_window
from trading.services.analysis.queries import fetch_account_analysis
from trading.services.analysis.risk_snapshots import fetch_latest_risk_snapshot

__all__ = [
    "fetch_account_analysis",
    "fetch_latest_risk_snapshot",
    "fetch_sleeve_performance_window",
]
