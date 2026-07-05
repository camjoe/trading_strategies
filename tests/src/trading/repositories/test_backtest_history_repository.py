from __future__ import annotations

from trading.repositories.backtest_history import BacktestRunRepository
from tests.support.repositories import insert_repository_account
from tests.support.strategies import strategy_id_for


def _account_id(conn, name: str = "backtest_acct") -> int:
    return insert_repository_account(conn, name=name)


def _insert_run(
    conn,
    *,
    account_id: int,
    strategy_name: str,
    end_date: str,
    start_date: str = "2026-01-01",
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO backtest_runs (account_id, strategy_id, start_date, end_date, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (account_id, strategy_id_for(conn, strategy_name), start_date, end_date, "2026-01-01T00:00:00Z"),
    )
    conn.commit()
    return cursor.lastrowid


def _insert_equity_snapshot(conn, *, run_id: int, snapshot_time: str, equity: float) -> None:
    conn.execute(
        """
        INSERT INTO backtest_equity_snapshots
            (run_id, snapshot_time, cash, market_value, equity, realized_pnl, unrealized_pnl)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (run_id, snapshot_time, equity, 0.0, equity, 0.0, 0.0),
    )
    conn.commit()


class TestFetchByStrategyWindow:
    def test_returns_empty_when_no_runs(self, conn) -> None:
        acct_id = _account_id(conn)
        rows = BacktestRunRepository(conn).fetch_by_strategy_window(
            account_id=acct_id,
            strategy_names=["trend"],
            start_day="2026-01-01",
            end_day="2026-12-31",
        )
        assert rows == []

    def test_returns_matching_run(self, conn) -> None:
        acct_id = _account_id(conn)
        run_id = _insert_run(conn, account_id=acct_id, strategy_name="trend", end_date="2026-06-01")
        _insert_equity_snapshot(conn, run_id=run_id, snapshot_time="2026-01-01T00:00:00Z", equity=10_000.0)
        _insert_equity_snapshot(conn, run_id=run_id, snapshot_time="2026-06-01T00:00:00Z", equity=11_000.0)

        rows = BacktestRunRepository(conn).fetch_by_strategy_window(
            account_id=acct_id,
            strategy_names=["trend"],
            start_day="2026-01-01",
            end_day="2026-12-31",
        )
        assert len(rows) == 1
        assert rows[0]["strategy_name"] == "trend"
        assert float(rows[0]["starting_equity"]) == 10_000.0
        assert float(rows[0]["ending_equity"]) == 11_000.0

    def test_filters_by_strategy_name(self, conn) -> None:
        acct_id = _account_id(conn)
        _insert_run(conn, account_id=acct_id, strategy_name="trend", end_date="2026-06-01")
        _insert_run(conn, account_id=acct_id, strategy_name="meanrev", end_date="2026-06-01")

        rows = BacktestRunRepository(conn).fetch_by_strategy_window(
            account_id=acct_id,
            strategy_names=["trend"],
            start_day="2026-01-01",
            end_day="2026-12-31",
        )
        assert len(rows) == 1
        assert rows[0]["strategy_name"] == "trend"

    def test_multiple_strategy_names_returned(self, conn) -> None:
        acct_id = _account_id(conn)
        _insert_run(conn, account_id=acct_id, strategy_name="trend", end_date="2026-06-01")
        _insert_run(conn, account_id=acct_id, strategy_name="meanrev", end_date="2026-06-01")

        rows = BacktestRunRepository(conn).fetch_by_strategy_window(
            account_id=acct_id,
            strategy_names=["trend", "meanrev"],
            start_day="2026-01-01",
            end_day="2026-12-31",
        )
        assert len(rows) == 2

    def test_filters_by_end_date_window(self, conn) -> None:
        acct_id = _account_id(conn)
        _insert_run(conn, account_id=acct_id, strategy_name="trend", end_date="2026-03-01")
        _insert_run(conn, account_id=acct_id, strategy_name="trend", end_date="2026-09-01")

        rows = BacktestRunRepository(conn).fetch_by_strategy_window(
            account_id=acct_id,
            strategy_names=["trend"],
            start_day="2026-07-01",
            end_day="2026-12-31",
        )
        assert len(rows) == 1
        assert rows[0]["strategy_name"] == "trend"

    def test_isolated_per_account(self, conn) -> None:
        acct_a = _account_id(conn, "acct_a")
        acct_b = _account_id(conn, "acct_b")
        _insert_run(conn, account_id=acct_a, strategy_name="trend", end_date="2026-06-01")
        _insert_run(conn, account_id=acct_b, strategy_name="trend", end_date="2026-06-01")

        rows = BacktestRunRepository(conn).fetch_by_strategy_window(
            account_id=acct_a,
            strategy_names=["trend"],
            start_day="2026-01-01",
            end_day="2026-12-31",
        )
        assert len(rows) == 1

    def test_starting_and_ending_equity_null_when_no_snapshots(self, conn) -> None:
        acct_id = _account_id(conn)
        _insert_run(conn, account_id=acct_id, strategy_name="trend", end_date="2026-06-01")
        rows = BacktestRunRepository(conn).fetch_by_strategy_window(
            account_id=acct_id,
            strategy_names=["trend"],
            start_day="2026-01-01",
            end_day="2026-12-31",
        )
        assert len(rows) == 1
        assert rows[0]["starting_equity"] is None
        assert rows[0]["ending_equity"] is None
