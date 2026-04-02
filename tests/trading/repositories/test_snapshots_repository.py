from __future__ import annotations

import pytest

from trading.services.accounts_service import create_account
from trading.repositories.snapshots_repository import (
    fetch_latest_snapshot_row,
    fetch_recent_equity_rows,
    fetch_snapshot_history_rows,
    insert_snapshot_row,
)


def _account_id(conn, name: str = "snap_acct") -> int:
    create_account(conn, name, "Trend", 5000.0, "SPY")
    row = conn.execute("SELECT id FROM accounts WHERE name = ?", (name,)).fetchone()
    return int(row["id"])


def _insert(conn, account_id: int, *, snapshot_time: str, equity: float) -> None:
    insert_snapshot_row(
        conn,
        account_id=account_id,
        snapshot_time=snapshot_time,
        cash=equity,
        market_value=0.0,
        equity=equity,
        realized_pnl=0.0,
        unrealized_pnl=0.0,
    )


class TestInsertSnapshotRow:
    def test_inserted_row_is_fetchable(self, conn) -> None:
        acct_id = _account_id(conn)
        insert_snapshot_row(
            conn,
            account_id=acct_id,
            snapshot_time="2026-01-01T10:00:00",
            cash=4500.0,
            market_value=500.0,
            equity=5000.0,
            realized_pnl=100.0,
            unrealized_pnl=50.0,
        )
        rows = fetch_snapshot_history_rows(conn, account_id=acct_id, limit=10)
        assert len(rows) == 1
        assert float(rows[0]["equity"]) == pytest.approx(5000.0)
        assert float(rows[0]["cash"]) == pytest.approx(4500.0)
        assert float(rows[0]["realized_pnl"]) == pytest.approx(100.0)


class TestFetchRecentEquityRows:
    def test_returns_newest_first(self, conn) -> None:
        acct_id = _account_id(conn)
        _insert(conn, acct_id, snapshot_time="2026-01-01T00:00:00", equity=1000.0)
        _insert(conn, acct_id, snapshot_time="2026-01-03T00:00:00", equity=1200.0)
        _insert(conn, acct_id, snapshot_time="2026-01-02T00:00:00", equity=1100.0)
        rows = fetch_recent_equity_rows(conn, account_id=acct_id, limit=3)
        equities = [float(r["equity"]) for r in rows]
        assert equities == pytest.approx([1200.0, 1100.0, 1000.0])

    def test_limit_respected(self, conn) -> None:
        acct_id = _account_id(conn)
        for i in range(5):
            _insert(conn, acct_id, snapshot_time=f"2026-01-0{i + 1}T00:00:00", equity=float(i * 100))
        rows = fetch_recent_equity_rows(conn, account_id=acct_id, limit=2)
        assert len(rows) == 2

    def test_empty_when_no_snapshots(self, conn) -> None:
        acct_id = _account_id(conn)
        assert fetch_recent_equity_rows(conn, account_id=acct_id, limit=10) == []

    def test_isolated_per_account(self, conn) -> None:
        acct_a = _account_id(conn, "snap_a")
        acct_b = _account_id(conn, "snap_b")
        _insert(conn, acct_a, snapshot_time="2026-01-01T00:00:00", equity=999.0)
        rows = fetch_recent_equity_rows(conn, account_id=acct_b, limit=10)
        assert rows == []


class TestFetchSnapshotHistoryRows:
    def test_returns_newest_first(self, conn) -> None:
        acct_id = _account_id(conn)
        _insert(conn, acct_id, snapshot_time="2026-01-01T00:00:00", equity=500.0)
        _insert(conn, acct_id, snapshot_time="2026-01-02T00:00:00", equity=600.0)
        rows = fetch_snapshot_history_rows(conn, account_id=acct_id, limit=10)
        assert float(rows[0]["equity"]) == pytest.approx(600.0)

    def test_all_columns_present(self, conn) -> None:
        acct_id = _account_id(conn)
        insert_snapshot_row(
            conn,
            account_id=acct_id,
            snapshot_time="2026-03-01T00:00:00",
            cash=3000.0,
            market_value=700.0,
            equity=3700.0,
            realized_pnl=200.0,
            unrealized_pnl=50.0,
        )
        row = fetch_snapshot_history_rows(conn, account_id=acct_id, limit=1)[0]
        assert row["snapshot_time"] == "2026-03-01T00:00:00"
        assert float(row["market_value"]) == pytest.approx(700.0)
        assert float(row["unrealized_pnl"]) == pytest.approx(50.0)


class TestFetchLatestSnapshotRow:
    def test_returns_none_when_empty(self, conn) -> None:
        acct_id = _account_id(conn)
        assert fetch_latest_snapshot_row(conn, account_id=acct_id) is None

    def test_returns_single_row_when_one_snapshot(self, conn) -> None:
        acct_id = _account_id(conn)
        _insert(conn, acct_id, snapshot_time="2026-01-10T00:00:00", equity=5500.0)
        row = fetch_latest_snapshot_row(conn, account_id=acct_id)
        assert row is not None
        assert float(row["equity"]) == pytest.approx(5500.0)

    def test_returns_most_recent_when_multiple(self, conn) -> None:
        acct_id = _account_id(conn)
        _insert(conn, acct_id, snapshot_time="2026-01-01T00:00:00", equity=100.0)
        _insert(conn, acct_id, snapshot_time="2026-01-03T00:00:00", equity=300.0)
        _insert(conn, acct_id, snapshot_time="2026-01-02T00:00:00", equity=200.0)
        row = fetch_latest_snapshot_row(conn, account_id=acct_id)
        assert float(row["equity"]) == pytest.approx(300.0)
