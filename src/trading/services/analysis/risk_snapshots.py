"""Risk-snapshot query flows for analysis consumers.

Owns read-only access to the latest account risk snapshot beneath the stable
``trading.services.analysis`` package surface.
"""

from __future__ import annotations

import sqlite3

from trading.models.books import RiskSnapshotRecord
from trading.repositories.risk import RiskSnapshotRepository


def fetch_latest_risk_snapshot(
    conn: sqlite3.Connection,
    *,
    account_id: int,
) -> RiskSnapshotRecord | None:
    if account_id <= 0:
        raise ValueError("account_id must be positive.")
    return RiskSnapshotRepository(conn).fetch_latest(account_id=account_id)
