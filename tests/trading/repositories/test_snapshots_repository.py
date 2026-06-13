from __future__ import annotations

import pytest

from trading.repositories.snapshots import EquitySnapshotRepository
from tests.support.repositories import insert_repository_account


def _account_id(conn, name: str = "snap_acct") -> int:
    return insert_repository_account(conn, name=name)


def _insert(conn, account_id: int, *, snapshot_time: str, equity: float) -> None:
    EquitySnapshotRepository(conn).insert(
        account_id=account_id,
        snapshot_time=snapshot_time,
        cash=equity,
        market_value=0.0,
        equity=equity,
        realized_pnl=0.0,
        unrealized_pnl=0.0,
    )


class TestInsert:
    def test_inserted_row_is_fetchable(self, conn) -> None:
        acct_id = _account_id(conn)
        repo = EquitySnapshotRepository(conn)
        repo.insert(
            account_id=acct_id,
            snapshot_time="2026-01-01T10:00:00",
            cash=4500.0,
            market_value=500.0,
            equity=5000.0,
            realized_pnl=100.0,
            unrealized_pnl=50.0,
        )
        rows = repo.fetch_history(account_id=acct_id, limit=10)
        assert len(rows) == 1
        assert rows[0].equity == pytest.approx(5000.0)
        assert rows[0].cash == pytest.approx(4500.0)
        assert rows[0].realized_pnl == pytest.approx(100.0)


class TestFetchRecentEquity:
    def test_returns_newest_first(self, conn) -> None:
        acct_id = _account_id(conn)
        _insert(conn, acct_id, snapshot_time="2026-01-01T00:00:00", equity=1000.0)
        _insert(conn, acct_id, snapshot_time="2026-01-03T00:00:00", equity=1200.0)
        _insert(conn, acct_id, snapshot_time="2026-01-02T00:00:00", equity=1100.0)
        equities = EquitySnapshotRepository(conn).fetch_recent_equity(account_id=acct_id, limit=3)
        assert equities == pytest.approx([1200.0, 1100.0, 1000.0])

    def test_limit_respected(self, conn) -> None:
        acct_id = _account_id(conn)
        for i in range(5):
            _insert(conn, acct_id, snapshot_time=f"2026-01-0{i + 1}T00:00:00", equity=float(i * 100))
        equities = EquitySnapshotRepository(conn).fetch_recent_equity(account_id=acct_id, limit=2)
        assert len(equities) == 2

    def test_empty_when_no_snapshots(self, conn) -> None:
        acct_id = _account_id(conn)
        assert EquitySnapshotRepository(conn).fetch_recent_equity(account_id=acct_id, limit=10) == []

    def test_isolated_per_account(self, conn) -> None:
        acct_a = _account_id(conn, "snap_a")
        acct_b = _account_id(conn, "snap_b")
        _insert(conn, acct_a, snapshot_time="2026-01-01T00:00:00", equity=999.0)
        assert EquitySnapshotRepository(conn).fetch_recent_equity(account_id=acct_b, limit=10) == []


class TestFetchHistory:
    def test_returns_newest_first(self, conn) -> None:
        acct_id = _account_id(conn)
        _insert(conn, acct_id, snapshot_time="2026-01-01T00:00:00", equity=500.0)
        _insert(conn, acct_id, snapshot_time="2026-01-02T00:00:00", equity=600.0)
        rows = EquitySnapshotRepository(conn).fetch_history(account_id=acct_id, limit=10)
        assert rows[0].equity == pytest.approx(600.0)

    def test_all_columns_present(self, conn) -> None:
        acct_id = _account_id(conn)
        EquitySnapshotRepository(conn).insert(
            account_id=acct_id,
            snapshot_time="2026-03-01T00:00:00",
            cash=3000.0,
            market_value=700.0,
            equity=3700.0,
            realized_pnl=200.0,
            unrealized_pnl=50.0,
        )
        row = EquitySnapshotRepository(conn).fetch_history(account_id=acct_id, limit=1)[0]
        assert row.snapshot_time == "2026-03-01T00:00:00"
        assert row.market_value == pytest.approx(700.0)
        assert row.unrealized_pnl == pytest.approx(50.0)


class TestFetchLatest:
    def test_returns_none_when_empty(self, conn) -> None:
        acct_id = _account_id(conn)
        assert EquitySnapshotRepository(conn).fetch_latest(account_id=acct_id) is None

    def test_returns_single_row_when_one_snapshot(self, conn) -> None:
        acct_id = _account_id(conn)
        _insert(conn, acct_id, snapshot_time="2026-01-10T00:00:00", equity=5500.0)
        row = EquitySnapshotRepository(conn).fetch_latest(account_id=acct_id)
        assert row is not None
        assert row.equity == pytest.approx(5500.0)

    def test_returns_most_recent_when_multiple(self, conn) -> None:
        acct_id = _account_id(conn)
        _insert(conn, acct_id, snapshot_time="2026-01-01T00:00:00", equity=100.0)
        _insert(conn, acct_id, snapshot_time="2026-01-03T00:00:00", equity=300.0)
        _insert(conn, acct_id, snapshot_time="2026-01-02T00:00:00", equity=200.0)
        row = EquitySnapshotRepository(conn).fetch_latest(account_id=acct_id)
        assert row is not None
        assert row.equity == pytest.approx(300.0)

    def test_full_record_fields_available(self, conn) -> None:
        acct_id = _account_id(conn, "details_acct")
        assert EquitySnapshotRepository(conn).fetch_latest(account_id=acct_id) is None

        EquitySnapshotRepository(conn).insert(
            account_id=acct_id,
            snapshot_time="2026-02-01T12:00:00",
            cash=1250.0,
            market_value=750.0,
            equity=2000.0,
            realized_pnl=120.0,
            unrealized_pnl=30.0,
        )

        row = EquitySnapshotRepository(conn).fetch_latest(account_id=acct_id)
        assert row is not None
        assert row.snapshot_time == "2026-02-01T12:00:00"
        assert row.cash == pytest.approx(1250.0)
        assert row.market_value == pytest.approx(750.0)
        assert row.realized_pnl == pytest.approx(120.0)
        assert row.unrealized_pnl == pytest.approx(30.0)


class TestSnapshotCounts:
    def test_count_between_and_count_apply_filters(self, conn) -> None:
        acct_a = _account_id(conn, "count_a")
        acct_b = _account_id(conn, "count_b")
        _insert(conn, acct_a, snapshot_time="2026-01-01T00:00:00", equity=100.0)
        _insert(conn, acct_a, snapshot_time="2026-01-02T00:00:00", equity=200.0)
        _insert(conn, acct_a, snapshot_time="2026-01-04T00:00:00", equity=400.0)
        _insert(conn, acct_b, snapshot_time="2026-01-02T00:00:00", equity=999.0)
        repo = EquitySnapshotRepository(conn)

        assert repo.fetch_count_between(
            account_id=acct_a,
            start_iso="2026-01-01T00:00:00",
            end_iso="2026-01-02T23:59:59",
        ) == 2
        assert repo.fetch_count(account_id=acct_a) == 3
        assert repo.fetch_count(account_id=acct_b) == 1
