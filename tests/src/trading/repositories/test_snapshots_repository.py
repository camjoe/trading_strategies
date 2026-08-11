from __future__ import annotations

import pytest

from tests.support.books import ensure_default_book_id
from tests.support.repositories import insert_repository_account
from trading.repositories.snapshots import EquitySnapshotRepository


def _account_id(conn, name: str = "snap_acct") -> int:
    return insert_repository_account(conn, name=name)


def _insert(conn, account_id: int, *, snapshot_time: str, equity: float) -> None:
    EquitySnapshotRepository(conn).insert_for_book(
        book_id=ensure_default_book_id(conn, account_id),
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
        repo.insert_for_book(
            book_id=ensure_default_book_id(conn, acct_id),
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


class TestFetchMaxEquity:
    def test_returns_the_highest_recorded_equity(self, conn) -> None:
        acct_id = _account_id(conn)
        _insert(conn, acct_id, snapshot_time="2026-01-01T00:00:00", equity=1000.0)
        _insert(conn, acct_id, snapshot_time="2026-01-02T00:00:00", equity=1500.0)
        _insert(conn, acct_id, snapshot_time="2026-01-03T00:00:00", equity=1200.0)

        assert EquitySnapshotRepository(conn).fetch_max_equity(account_id=acct_id) == pytest.approx(1500.0)

    def test_returns_none_with_no_snapshots(self, conn) -> None:
        acct_id = _account_id(conn)

        assert EquitySnapshotRepository(conn).fetch_max_equity(account_id=acct_id) is None


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
        EquitySnapshotRepository(conn).insert_for_book(
            book_id=ensure_default_book_id(conn, acct_id),
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

        EquitySnapshotRepository(conn).insert_for_book(
            book_id=ensure_default_book_id(conn, acct_id),
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

        assert (
            repo.fetch_count_between(
                account_id=acct_a,
                start_iso="2026-01-01T00:00:00",
                end_iso="2026-01-02T23:59:59",
            )
            == 2
        )
        assert repo.fetch_count(account_id=acct_a) == 3
        assert repo.fetch_count(account_id=acct_b) == 1


class TestWindowReads:
    def test_earliest_and_boundary_reads(self, conn) -> None:
        acct_id = _account_id(conn, "snap_window_acct")
        _insert(conn, acct_id, snapshot_time="2026-02-01T00:00:00Z", equity=1000.0)
        _insert(conn, acct_id, snapshot_time="2026-02-05T00:00:00Z", equity=1050.0)
        _insert(conn, acct_id, snapshot_time="2026-02-10T00:00:00Z", equity=1100.0)
        repo = EquitySnapshotRepository(conn)

        assert repo.fetch_earliest(account_id=acct_id).equity == pytest.approx(1000.0)
        # First at/after the window start snaps forward to the next available row.
        assert repo.fetch_first_at_or_after(account_id=acct_id, iso="2026-02-03T00:00:00Z").equity == pytest.approx(
            1050.0
        )
        # Last at/before the window end snaps back to the prior available row.
        assert repo.fetch_last_at_or_before(account_id=acct_id, iso="2026-02-07T00:00:00Z").equity == pytest.approx(
            1050.0
        )

    def test_boundary_reads_return_none_outside_range(self, conn) -> None:
        acct_id = _account_id(conn, "snap_window_empty")
        _insert(conn, acct_id, snapshot_time="2026-02-05T00:00:00Z", equity=1050.0)
        repo = EquitySnapshotRepository(conn)

        assert repo.fetch_first_at_or_after(account_id=acct_id, iso="2026-03-01T00:00:00Z") is None
        assert repo.fetch_last_at_or_before(account_id=acct_id, iso="2026-01-01T00:00:00Z") is None


class TestBookDateBoundReads:
    """The per-book date-bounded reads, over deliberately mixed timestamp spellings.

    Rows written before the canonical form was enforced can carry a bare or
    ``+00:00`` suffix, and the bound is compared as a string, so the date reads
    have to hold for every spelling of the same instant.
    """

    def _book_id(self, conn, account_id: int) -> int:
        from tests.support.books import ensure_default_book_id

        return ensure_default_book_id(conn, account_id)

    def _seed_mixed_spellings(self, conn, account_id: int) -> int:
        book_id = self._book_id(conn, account_id)
        repo = EquitySnapshotRepository(conn)
        for snapshot_time, equity in (
            ("2026-02-03T16:00:00Z", 1000.0),
            ("2026-02-04T16:00:00+00:00", 1050.0),
            ("2026-02-05T16:00:00", 1100.0),
        ):
            repo.insert_for_book(
                book_id=book_id,
                snapshot_time=snapshot_time,
                cash=equity,
                market_value=0.0,
                equity=equity,
                realized_pnl=0.0,
                unrealized_pnl=0.0,
            )
        return book_id

    def test_on_or_before_includes_the_whole_named_day(self, conn) -> None:
        acct_id = _account_id(conn, "snap_bound_incl")
        book_id = self._seed_mixed_spellings(conn, acct_id)
        repo = EquitySnapshotRepository(conn)

        # The 2026-02-05 row is naive-suffixed; the bound must still include it.
        assert repo.fetch_last_for_book_on_or_before_date(
            book_id=book_id, date_str="2026-02-05"
        ).equity == pytest.approx(1100.0)
        # The 2026-02-04 row carries +00:00.
        assert repo.fetch_last_for_book_on_or_before_date(
            book_id=book_id, date_str="2026-02-04"
        ).equity == pytest.approx(1050.0)

    def test_before_date_excludes_the_whole_named_day(self, conn) -> None:
        acct_id = _account_id(conn, "snap_bound_excl")
        book_id = self._seed_mixed_spellings(conn, acct_id)
        repo = EquitySnapshotRepository(conn)

        assert repo.fetch_last_for_book_before_date(book_id=book_id, date_str="2026-02-05").equity == pytest.approx(
            1050.0
        )
        assert repo.fetch_last_for_book_before_date(book_id=book_id, date_str="2026-02-03") is None

    def test_returns_none_before_any_snapshot(self, conn) -> None:
        acct_id = _account_id(conn, "snap_bound_none")
        book_id = self._seed_mixed_spellings(conn, acct_id)

        assert (
            EquitySnapshotRepository(conn).fetch_last_for_book_on_or_before_date(
                book_id=book_id, date_str="2026-02-02"
            )
            is None
        )
