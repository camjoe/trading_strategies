from __future__ import annotations

import pytest

from trading.repositories.daily_metrics import DailyMetricsRepository
from tests.support.repositories import insert_repository_account
from tests.support.sleeves import insert_test_book


def _account_id(conn, name: str = "metrics_acct") -> int:
    return insert_repository_account(conn, name=name)


def _sleeve_id(conn, account_id: int) -> int:
    return insert_test_book(conn, account_id=account_id)


def _upsert(conn, *, account_id: int, book_id: int | None, metric_date: str, return_pct: float = 1.0) -> int:
    return DailyMetricsRepository(conn).upsert(
        account_id=account_id,
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


class TestUpsert:
    def test_insert_returns_id(self, conn) -> None:
        acct_id = _account_id(conn)
        row_id = _upsert(conn, account_id=acct_id, book_id=None, metric_date="2026-01-01")
        assert row_id > 0

    def test_second_upsert_returns_same_id(self, conn) -> None:
        acct_id = _account_id(conn)
        id_a = _upsert(conn, account_id=acct_id, book_id=None, metric_date="2026-01-01")
        id_b = _upsert(conn, account_id=acct_id, book_id=None, metric_date="2026-01-01", return_pct=2.0)
        assert id_a == id_b

    def test_upsert_updates_existing_values(self, conn) -> None:
        acct_id = _account_id(conn)
        _upsert(conn, account_id=acct_id, book_id=None, metric_date="2026-01-01", return_pct=1.0)
        _upsert(conn, account_id=acct_id, book_id=None, metric_date="2026-01-01", return_pct=9.9)
        rows = DailyMetricsRepository(conn).fetch_for_account(account_id=acct_id, limit=10)
        assert len(rows) == 1
        assert rows[0].return_pct == pytest.approx(9.9)

    def test_sleeve_and_portfolio_rows_are_distinct(self, conn) -> None:
        acct_id = _account_id(conn)
        bk_id = _sleeve_id(conn, acct_id)
        id_sleeve = _upsert(conn, account_id=acct_id, book_id=bk_id, metric_date="2026-01-01")
        id_portfolio = _upsert(conn, account_id=acct_id, book_id=None, metric_date="2026-01-01")
        assert id_sleeve != id_portfolio

    def test_raises_on_insert_failure(self) -> None:
        class _Cursor:
            lastrowid = None
            rowcount = 1  # pretend the default-book bootstrap insert succeeded

            def fetchone(self):
                return None

            def fetchall(self):
                return []

        class _Conn:
            def execute(self, *_a, **_kw):
                return _Cursor()

            def commit(self):
                pass

        with pytest.raises(ValueError, match="Expected daily_metrics id after upsert"):
            DailyMetricsRepository(_Conn()).upsert(
                account_id=1,
                book_id=None,
                metric_date="2026-01-01",
                return_pct=None,
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


class TestFetchForAccount:
    def test_empty_when_no_metrics(self, conn) -> None:
        acct_id = _account_id(conn)
        assert DailyMetricsRepository(conn).fetch_for_account(account_id=acct_id, limit=10) == []

    def test_only_returns_rows_for_requested_account(self, conn) -> None:
        acct_a = _account_id(conn, "acct_a")
        acct_b = _account_id(conn, "acct_b")
        _upsert(conn, account_id=acct_a, book_id=None, metric_date="2026-01-01", return_pct=1.0)
        _upsert(conn, account_id=acct_b, book_id=None, metric_date="2026-01-01", return_pct=2.0)
        rows = DailyMetricsRepository(conn).fetch_for_account(account_id=acct_a, limit=10)
        assert len(rows) == 1
        assert rows[0].return_pct == pytest.approx(1.0)

    def test_limit_is_respected(self, conn) -> None:
        acct_id = _account_id(conn)
        for day in ("2026-01-01", "2026-01-02", "2026-01-03"):
            _upsert(conn, account_id=acct_id, book_id=None, metric_date=day)
        rows = DailyMetricsRepository(conn).fetch_for_account(account_id=acct_id, limit=2)
        assert len(rows) == 2

    def test_ordered_by_metric_date_desc(self, conn) -> None:
        acct_id = _account_id(conn)
        _upsert(conn, account_id=acct_id, book_id=None, metric_date="2026-01-01")
        _upsert(conn, account_id=acct_id, book_id=None, metric_date="2026-01-03")
        _upsert(conn, account_id=acct_id, book_id=None, metric_date="2026-01-02")
        rows = DailyMetricsRepository(conn).fetch_for_account(account_id=acct_id, limit=10)
        dates = [r.metric_date for r in rows]
        assert dates == sorted(dates, reverse=True)


class TestFetchForSleeve:
    def test_empty_when_no_sleeve_metrics(self, conn) -> None:
        acct_id = _account_id(conn)
        bk_id = _sleeve_id(conn, acct_id)
        assert DailyMetricsRepository(conn).fetch_for_book(book_id=bk_id, limit=10) == []

    def test_excludes_portfolio_level_rows(self, conn) -> None:
        acct_id = _account_id(conn)
        bk_id = _sleeve_id(conn, acct_id)
        _upsert(conn, account_id=acct_id, book_id=None, metric_date="2026-01-01")
        _upsert(conn, account_id=acct_id, book_id=bk_id, metric_date="2026-01-01", return_pct=3.0)
        rows = DailyMetricsRepository(conn).fetch_for_book(book_id=bk_id, limit=10)
        assert len(rows) == 1
        assert rows[0].return_pct == pytest.approx(3.0)


class TestFetchForSleeveWindow:
    def test_returns_only_rows_within_window(self, conn) -> None:
        acct_id = _account_id(conn)
        bk_id = _sleeve_id(conn, acct_id)
        _upsert(conn, account_id=acct_id, book_id=bk_id, metric_date="2026-01-01")
        _upsert(conn, account_id=acct_id, book_id=bk_id, metric_date="2026-01-05")
        _upsert(conn, account_id=acct_id, book_id=bk_id, metric_date="2026-01-10")
        rows = DailyMetricsRepository(conn).fetch_for_book_window(
            book_id=bk_id, start_date="2026-01-03", end_date="2026-01-07"
        )
        assert len(rows) == 1
        assert rows[0].metric_date == "2026-01-05"

    def test_window_boundaries_are_inclusive(self, conn) -> None:
        acct_id = _account_id(conn)
        bk_id = _sleeve_id(conn, acct_id)
        _upsert(conn, account_id=acct_id, book_id=bk_id, metric_date="2026-01-01")
        _upsert(conn, account_id=acct_id, book_id=bk_id, metric_date="2026-01-05")
        rows = DailyMetricsRepository(conn).fetch_for_book_window(
            book_id=bk_id, start_date="2026-01-01", end_date="2026-01-05"
        )
        assert len(rows) == 2

    def test_ordered_by_metric_date_asc(self, conn) -> None:
        acct_id = _account_id(conn)
        bk_id = _sleeve_id(conn, acct_id)
        for day in ("2026-01-03", "2026-01-01", "2026-01-02"):
            _upsert(conn, account_id=acct_id, book_id=bk_id, metric_date=day)
        rows = DailyMetricsRepository(conn).fetch_for_book_window(
            book_id=bk_id, start_date="2026-01-01", end_date="2026-01-03"
        )
        dates = [r.metric_date for r in rows]
        assert dates == sorted(dates)
