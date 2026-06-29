"""Portfolio risk-snapshot query flows for analysis consumers.

Owns read-only access to the latest portfolio risk snapshot beneath the stable
``trading.services.analysis`` package surface.
"""

from __future__ import annotations

import sqlite3

from trading.models.portfolio.portfolio_risk_snapshot_record import PortfolioRiskSnapshotRecord
from trading.repositories.portfolio_risk_snapshots import PortfolioRiskSnapshotRepository


def fetch_latest_risk_snapshot(
    conn: sqlite3.Connection,
    *,
    account_id: int,
) -> PortfolioRiskSnapshotRecord | None:
    if account_id <= 0:
        raise ValueError("account_id must be positive.")
    return PortfolioRiskSnapshotRepository(conn).fetch_latest(account_id=account_id)
