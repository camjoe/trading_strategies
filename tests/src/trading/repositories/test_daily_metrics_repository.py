from __future__ import annotations

import pytest

from tests.support.books import insert_test_book
from tests.support.repositories import insert_repository_account
from trading.repositories.daily_metrics import DailyMetricsRepository


def _account_id(conn, name: str = "metrics_acct") -> int:
    return insert_repository_account(conn, name=name)


def _book_id(conn, account_id: int, name: str = "core") -> int:
    return insert_test_book(conn, account_id=account_id, name=name)


def _account_with_book(conn, name: str = "metrics_acct") -> tuple[int, int]:
    account_id = _account_id(conn, name)
    return account_id, _book_id(conn, account_id)


def _upsert(conn, *, book_id: int, metric_date: str, return_pct: float = 1.0) -> None:
    DailyMetricsRepository(conn).upsert(
        book_id=book_id,
        metric_date=metric_date,
        return_pct=return_pct,
        drawdown_pct=-0.5,
        turnover_pct=2.0,
        slippage_bps=5.0,
        hit_rate=0.6,
        expectancy=0.1,
        risk_adjusted_score=0.8,
        trade_count=5,
        fees_total=2.0,
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )


def _stored_ids(conn, book_id: int) -> list[int]:
    return [int(r["id"]) for r in conn.execute("SELECT id FROM daily_metrics WHERE book_id = ?", (book_id,))]


class TestUpsert:
    def test_insert_stores_one_row(self, conn) -> None:
        _, bk_id = _account_with_book(conn)
        _upsert(conn, book_id=bk_id, metric_date="2026-01-01")
        assert len(_stored_ids(conn, bk_id)) == 1

    def test_second_upsert_reuses_the_same_row(self, conn) -> None:
        _, bk_id = _account_with_book(conn)
        _upsert(conn, book_id=bk_id, metric_date="2026-01-01")
        before = _stored_ids(conn, bk_id)
        _upsert(conn, book_id=bk_id, metric_date="2026-01-01", return_pct=2.0)
        assert _stored_ids(conn, bk_id) == before

    def test_upsert_updates_existing_values(self, conn) -> None:
        acct_id, bk_id = _account_with_book(conn)
        _upsert(conn, book_id=bk_id, metric_date="2026-01-01", return_pct=1.0)
        _upsert(conn, book_id=bk_id, metric_date="2026-01-01", return_pct=9.9)
        rows = DailyMetricsRepository(conn).fetch_book_rows_for_account(account_id=acct_id, limit=10)
        assert len(rows) == 1
        assert rows[0].return_pct == pytest.approx(9.9)

    def test_rows_are_distinct_per_book(self, conn) -> None:
        acct_id, bk_a = _account_with_book(conn)
        bk_b = _book_id(conn, acct_id, name="second")
        _upsert(conn, book_id=bk_a, metric_date="2026-01-01")
        _upsert(conn, book_id=bk_b, metric_date="2026-01-01")
        assert _stored_ids(conn, bk_a) != _stored_ids(conn, bk_b)


class TestFetchForAccount:
    def test_empty_when_no_metrics(self, conn) -> None:
        acct_id = _account_id(conn)
        assert DailyMetricsRepository(conn).fetch_book_rows_for_account(account_id=acct_id, limit=10) == []

    def test_only_returns_rows_for_requested_account(self, conn) -> None:
        acct_a, bk_a = _account_with_book(conn, "acct_a")
        _, bk_b = _account_with_book(conn, "acct_b")
        _upsert(conn, book_id=bk_a, metric_date="2026-01-01", return_pct=1.0)
        _upsert(conn, book_id=bk_b, metric_date="2026-01-01", return_pct=2.0)
        rows = DailyMetricsRepository(conn).fetch_book_rows_for_account(account_id=acct_a, limit=10)
        assert len(rows) == 1
        assert rows[0].return_pct == pytest.approx(1.0)

    def test_limit_is_respected(self, conn) -> None:
        acct_id, bk_id = _account_with_book(conn)
        for day in ("2026-01-01", "2026-01-02", "2026-01-03"):
            _upsert(conn, book_id=bk_id, metric_date=day)
        rows = DailyMetricsRepository(conn).fetch_book_rows_for_account(account_id=acct_id, limit=2)
        assert len(rows) == 2

    def test_ordered_by_metric_date_desc(self, conn) -> None:
        acct_id, bk_id = _account_with_book(conn)
        _upsert(conn, book_id=bk_id, metric_date="2026-01-01")
        _upsert(conn, book_id=bk_id, metric_date="2026-01-03")
        _upsert(conn, book_id=bk_id, metric_date="2026-01-02")
        rows = DailyMetricsRepository(conn).fetch_book_rows_for_account(account_id=acct_id, limit=10)
        dates = [r.metric_date for r in rows]
        assert dates == sorted(dates, reverse=True)


class TestFetchForBook:
    def test_empty_when_no_book_metrics(self, conn) -> None:
        acct_id = _account_id(conn)
        bk_id = _book_id(conn, acct_id)
        assert DailyMetricsRepository(conn).fetch_for_book(book_id=bk_id, limit=10) == []

    def test_excludes_rows_from_the_accounts_other_books(self, conn) -> None:
        acct_id, bk_id = _account_with_book(conn)
        other_id = _book_id(conn, acct_id, name="other")
        _upsert(conn, book_id=other_id, metric_date="2026-01-01")
        _upsert(conn, book_id=bk_id, metric_date="2026-01-01", return_pct=3.0)
        rows = DailyMetricsRepository(conn).fetch_for_book(book_id=bk_id, limit=10)
        assert len(rows) == 1
        assert rows[0].return_pct == pytest.approx(3.0)


class TestFetchRecentReturnsForBook:
    def _upsert_return(self, conn, *, book_id, metric_date, return_pct) -> None:
        DailyMetricsRepository(conn).upsert(
            book_id=book_id,
            metric_date=metric_date,
            return_pct=return_pct,
            drawdown_pct=None,
            turnover_pct=None,
            slippage_bps=None,
            hit_rate=None,
            expectancy=None,
            risk_adjusted_score=None,
            trade_count=None,
            fees_total=None,
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
        )

    def test_returns_only_dates_before_the_boundary(self, conn) -> None:
        acct_id = _account_id(conn)
        bk_id = _book_id(conn, acct_id)
        self._upsert_return(conn, book_id=bk_id, metric_date="2026-01-01", return_pct=1.0)
        self._upsert_return(conn, book_id=bk_id, metric_date="2026-01-02", return_pct=2.0)
        self._upsert_return(conn, book_id=bk_id, metric_date="2026-01-03", return_pct=3.0)
        returns = DailyMetricsRepository(conn).fetch_recent_returns_for_book(
            book_id=bk_id, before_date="2026-01-03", limit=10
        )
        assert returns == [2.0, 1.0]  # strictly before 01-03, most-recent-first

    def test_most_recent_first_and_limited(self, conn) -> None:
        acct_id = _account_id(conn)
        bk_id = _book_id(conn, acct_id)
        for day, ret in (("2026-01-01", 1.0), ("2026-01-02", 2.0), ("2026-01-03", 3.0), ("2026-01-04", 4.0)):
            self._upsert_return(conn, book_id=bk_id, metric_date=day, return_pct=ret)
        returns = DailyMetricsRepository(conn).fetch_recent_returns_for_book(
            book_id=bk_id, before_date="2026-01-05", limit=2
        )
        assert returns == [4.0, 3.0]

    def test_excludes_null_returns(self, conn) -> None:
        acct_id = _account_id(conn)
        bk_id = _book_id(conn, acct_id)
        self._upsert_return(conn, book_id=bk_id, metric_date="2026-01-01", return_pct=None)
        self._upsert_return(conn, book_id=bk_id, metric_date="2026-01-02", return_pct=2.0)
        returns = DailyMetricsRepository(conn).fetch_recent_returns_for_book(
            book_id=bk_id, before_date="2026-01-03", limit=10
        )
        assert returns == [2.0]  # the NULL-return day is skipped

    def test_isolated_per_book(self, conn) -> None:
        acct_id = _account_id(conn)
        bk_a = insert_test_book(conn, account_id=acct_id, name="book_a")
        bk_b = insert_test_book(conn, account_id=acct_id, name="book_b")
        self._upsert_return(conn, book_id=bk_a, metric_date="2026-01-01", return_pct=1.0)
        self._upsert_return(conn, book_id=bk_b, metric_date="2026-01-01", return_pct=9.0)
        returns = DailyMetricsRepository(conn).fetch_recent_returns_for_book(
            book_id=bk_a, before_date="2026-01-02", limit=10
        )
        assert returns == [1.0]


class TestFetchForBookWindow:
    def test_returns_only_rows_within_window(self, conn) -> None:
        acct_id = _account_id(conn)
        bk_id = _book_id(conn, acct_id)
        _upsert(conn, book_id=bk_id, metric_date="2026-01-01")
        _upsert(conn, book_id=bk_id, metric_date="2026-01-05")
        _upsert(conn, book_id=bk_id, metric_date="2026-01-10")
        rows = DailyMetricsRepository(conn).fetch_for_book_window(
            book_id=bk_id, start_date="2026-01-03", end_date="2026-01-07"
        )
        assert len(rows) == 1
        assert rows[0].metric_date == "2026-01-05"

    def test_window_boundaries_are_inclusive(self, conn) -> None:
        acct_id = _account_id(conn)
        bk_id = _book_id(conn, acct_id)
        _upsert(conn, book_id=bk_id, metric_date="2026-01-01")
        _upsert(conn, book_id=bk_id, metric_date="2026-01-05")
        rows = DailyMetricsRepository(conn).fetch_for_book_window(
            book_id=bk_id, start_date="2026-01-01", end_date="2026-01-05"
        )
        assert len(rows) == 2

    def test_ordered_by_metric_date_asc(self, conn) -> None:
        acct_id = _account_id(conn)
        bk_id = _book_id(conn, acct_id)
        for day in ("2026-01-03", "2026-01-01", "2026-01-02"):
            _upsert(conn, book_id=bk_id, metric_date=day)
        rows = DailyMetricsRepository(conn).fetch_for_book_window(
            book_id=bk_id, start_date="2026-01-01", end_date="2026-01-03"
        )
        dates = [r.metric_date for r in rows]
        assert dates == sorted(dates)
