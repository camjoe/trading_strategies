from __future__ import annotations

import pytest
from fastapi import HTTPException

from paper_trading_web.backend.services import require_account_row
from paper_trading_web.backend.services import db as services_db
from trading.services.accounts import get_latest_account_snapshot


def test_db_conn_context_yields_and_closes_connection() -> None:
    with services_db.db_conn() as conn:
        assert conn.execute("SELECT 1 AS value").fetchone()["value"] == 1

    with pytest.raises(Exception):
        conn.execute("SELECT 1")


def test_require_account_row_found_and_missing(conn, create_account_row) -> None:
    create_account_row("acct_lookup")

    row = require_account_row(conn, "acct_lookup")
    assert row["name"] == "acct_lookup"

    with pytest.raises(HTTPException) as exc_info:
        require_account_row(conn, "missing")
    assert exc_info.value.status_code == 404


def test_get_latest_account_snapshot_prefers_latest_id_for_same_timestamp(conn, create_account_row) -> None:
    account_id = create_account_row("acct_snapshots")
    conn.execute(
        """
        INSERT INTO equity_snapshots (
            account_id, snapshot_time, cash, market_value, equity, realized_pnl, unrealized_pnl
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (account_id, "2026-01-01T00:00:00Z", 1000.0, 100.0, 1100.0, 0.0, 0.0),
    )
    conn.execute(
        """
        INSERT INTO equity_snapshots (
            account_id, snapshot_time, cash, market_value, equity, realized_pnl, unrealized_pnl
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (account_id, "2026-01-01T00:00:00Z", 1000.0, 250.0, 1250.0, 0.0, 0.0),
    )
    conn.commit()

    latest = get_latest_account_snapshot(conn, account_id)
    assert latest is not None
    assert latest.equity == 1250.0
