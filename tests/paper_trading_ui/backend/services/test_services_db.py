from __future__ import annotations

import pytest
from fastapi import HTTPException

from paper_trading_ui.backend.services import db as services_db

from tests.paper_trading_ui.backend.services._service_test_utils import create_test_account


def test_db_conn_context_yields_and_closes_connection() -> None:
    with services_db.db_conn() as conn:
        assert conn.execute("SELECT 1 AS value").fetchone()["value"] == 1

    with pytest.raises(Exception):
        conn.execute("SELECT 1")


def test_get_account_row_found_and_missing(conn) -> None:
    create_test_account(conn, "acct_lookup")

    row = services_db.get_account_row(conn, "acct_lookup")
    assert row["name"] == "acct_lookup"

    with pytest.raises(HTTPException) as exc_info:
        services_db.get_account_row(conn, "missing")
    assert exc_info.value.status_code == 404


def test_get_latest_snapshot_row_prefers_latest_id_for_same_timestamp(conn) -> None:
    account_id = create_test_account(conn, "acct_snapshots")
    conn.execute(
        """
        INSERT INTO equity_snapshots (account_id, snapshot_time, cash, market_value, equity, realized_pnl, unrealized_pnl)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (account_id, "2026-01-01T00:00:00Z", 1000.0, 100.0, 1100.0, 0.0, 0.0),
    )
    conn.execute(
        """
        INSERT INTO equity_snapshots (account_id, snapshot_time, cash, market_value, equity, realized_pnl, unrealized_pnl)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (account_id, "2026-01-01T00:00:00Z", 1000.0, 250.0, 1250.0, 0.0, 0.0),
    )
    conn.commit()

    latest = services_db.fetch_latest_snapshot_row(conn, account_id)
    assert latest is not None
    assert float(latest["equity"]) == 1250.0
