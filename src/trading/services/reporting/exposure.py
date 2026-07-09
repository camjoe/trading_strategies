"""Operator-facing printed view of the cross-account exposure rollup.

Presentation only: the payload contract and aggregation live in
``trading.services.analysis.exposure``.
"""

from __future__ import annotations

import sqlite3

from trading.models.portfolio.account_exposure import AccountExposure
from trading.models.portfolio.portfolio_exposure_rollup import PortfolioExposureRollup
from trading.services.analysis.exposure import fetch_portfolio_exposure


def _account_line(exposure: AccountExposure) -> str:
    if exposure.snapshot_time is None:
        return f"- {exposure.account_name} | no snapshots yet | positions={exposure.position_count}"
    assert exposure.equity is not None
    assert exposure.cash is not None
    assert exposure.market_value is not None
    return (
        f"- {exposure.account_name} | as_of={exposure.snapshot_time} | "
        f"equity={exposure.equity:.2f} cash={exposure.cash:.2f} "
        f"mv={exposure.market_value:.2f} positions={exposure.position_count}"
    )


def show_portfolio_exposure(conn: sqlite3.Connection) -> PortfolioExposureRollup:
    """Print the cross-account exposure rollup and return the payload."""
    rollup = fetch_portfolio_exposure(conn)

    if not rollup.accounts:
        print("No accounts found.")
        return rollup

    print("Portfolio exposure rollup (latest snapshot per account):")
    for exposure in rollup.accounts:
        print(_account_line(exposure))
    print(
        f"Totals ({rollup.accounts_with_snapshots} of {len(rollup.accounts)} accounts with snapshots): "
        f"equity={rollup.total_equity:.2f} cash={rollup.total_cash:.2f} "
        f"mv={rollup.total_market_value:.2f}"
    )
    return rollup


__all__ = ["show_portfolio_exposure"]
