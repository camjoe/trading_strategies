from __future__ import annotations

import sqlite3

import pytest

from paper_trading_web.backend.services import require_account_row
from paper_trading_web.backend.services import db as services_db
from trading.domain.exceptions import NotFoundError
from trading.repositories.snapshots import EquitySnapshotRepository
from trading.services.accounts import get_latest_account_snapshot


def test_db_conn_context_yields_and_closes_connection(conn) -> None:  # noqa: ARG001
    # `conn` pins an isolated at-head backend; db_conn() must never run
    # against the developer's real configured database.
    with services_db.db_conn() as managed_conn:
        assert managed_conn.execute("SELECT 1 AS value").fetchone()["value"] == 1

    with pytest.raises(Exception):
        managed_conn.execute("SELECT 1")


def test_require_account_row_found_and_missing(conn, create_account_row) -> None:
    create_account_row("acct_lookup")

    row = require_account_row(conn, "acct_lookup")
    assert row["name"] == "acct_lookup"

    with pytest.raises(NotFoundError):
        require_account_row(conn, "missing")


def test_get_latest_account_snapshot_returns_newest_time_and_rejects_duplicates(conn, create_account_row) -> None:
    account_id = create_account_row("acct_snapshots")
    repo = EquitySnapshotRepository(conn)
    repo.insert(
        account_id=account_id,
        snapshot_time="2026-01-01T00:00:00Z",
        cash=1000.0,
        market_value=100.0,
        equity=1100.0,
        realized_pnl=0.0,
        unrealized_pnl=0.0,
    )
    repo.insert(
        account_id=account_id,
        snapshot_time="2026-01-02T00:00:00Z",
        cash=1000.0,
        market_value=250.0,
        equity=1250.0,
        realized_pnl=0.0,
        unrealized_pnl=0.0,
    )

    latest = get_latest_account_snapshot(conn, account_id)
    assert latest is not None
    assert latest.equity == 1250.0

    # Book-keyed snapshots are unique per (book, snapshot_time): same-timestamp
    # duplicates are now a constraint violation rather than a tie to break.
    with pytest.raises(sqlite3.IntegrityError):
        repo.insert(
            account_id=account_id,
            snapshot_time="2026-01-02T00:00:00Z",
            cash=1.0,
            market_value=1.0,
            equity=1.0,
            realized_pnl=0.0,
            unrealized_pnl=0.0,
        )
