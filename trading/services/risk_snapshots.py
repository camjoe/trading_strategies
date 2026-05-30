from __future__ import annotations

import sqlite3

from trading.repositories.portfolio_risk_snapshots import fetch_latest_portfolio_risk_snapshot


def fetch_latest_risk_snapshot(
    conn: sqlite3.Connection,
    *,
    account_id: int,
) -> sqlite3.Row | None:
    if account_id <= 0:
        raise ValueError("account_id must be positive.")
    return fetch_latest_portfolio_risk_snapshot(conn, account_id=account_id)
