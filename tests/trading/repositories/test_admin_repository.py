from __future__ import annotations

from trading.repositories.admin import (
    delete_accounts_by_ids,
    delete_backtest_equity_snapshots_by_run_ids,
    delete_backtest_runs_by_account_ids,
    delete_backtest_trades_by_run_ids,
    delete_equity_snapshots_by_account_ids,
    delete_promotion_review_events_by_review_ids,
    delete_promotion_reviews_by_account_ids,
    delete_trades_by_account_ids,
    delete_walk_forward_group_runs_by_group_ids,
    delete_walk_forward_groups_by_account_ids,
    fetch_backtest_run_ids_for_account_ids,
    fetch_promotion_review_ids_for_account_ids,
    fetch_row_count,
    fetch_walk_forward_group_ids_for_account_ids,
)
from tests.support.repositories import insert_repository_account


def _account_id(conn, name: str = "admin_acct") -> int:
    return insert_repository_account(conn, name=name)


def _insert_backtest_run(conn, *, account_id: int, strategy_name: str = "trend") -> int:
    cursor = conn.execute(
        "INSERT INTO backtest_runs (account_id, strategy_name, start_date, end_date, created_at) VALUES (?,?,?,?,?)",
        (account_id, strategy_name, "2026-01-01", "2026-06-01", "2026-01-01T00:00:00Z"),
    )
    conn.commit()
    return cursor.lastrowid


def _insert_equity_snapshot(conn, *, account_id: int, snapshot_time: str = "2026-01-01T00:00:00Z") -> None:
    conn.execute(
        "INSERT INTO equity_snapshots (account_id, snapshot_time, cash, market_value, equity, realized_pnl, unrealized_pnl) VALUES (?,?,?,?,?,?,?)",
        (account_id, snapshot_time, 1000.0, 0.0, 1000.0, 0.0, 0.0),
    )
    conn.commit()


def _insert_trade(conn, *, account_id: int) -> None:
    conn.execute(
        "INSERT INTO trades (account_id, ticker, side, qty, price, fee, trade_time) VALUES (?,?,?,?,?,?,?)",
        (account_id, "AAPL", "buy", 1.0, 100.0, 0.0, "2026-01-01T10:00:00Z"),
    )
    conn.commit()


class TestFetchRowCount:
    def test_returns_zero_for_empty_table(self, conn) -> None:
        acct_id = _account_id(conn)
        count = fetch_row_count(conn, "trades", "account_id", (acct_id,))
        assert count == 0

    def test_counts_matching_rows(self, conn) -> None:
        acct_id = _account_id(conn)
        _insert_trade(conn, account_id=acct_id)
        _insert_trade(conn, account_id=acct_id)
        count = fetch_row_count(conn, "trades", "account_id", (acct_id,))
        assert count == 2

    def test_only_counts_matching_rows(self, conn) -> None:
        acct_a = _account_id(conn, "acct_a")
        acct_b = _account_id(conn, "acct_b")
        _insert_trade(conn, account_id=acct_a)
        _insert_trade(conn, account_id=acct_b)
        assert fetch_row_count(conn, "trades", "account_id", (acct_a,)) == 1


class TestFetchBacktestRunIdsForAccountIds:
    def test_returns_empty_tuple_for_no_runs(self, conn) -> None:
        acct_id = _account_id(conn)
        assert fetch_backtest_run_ids_for_account_ids(conn, (acct_id,)) == ()

    def test_returns_run_ids(self, conn) -> None:
        acct_id = _account_id(conn)
        run_id = _insert_backtest_run(conn, account_id=acct_id)
        ids = fetch_backtest_run_ids_for_account_ids(conn, (acct_id,))
        assert run_id in ids

    def test_spans_multiple_accounts(self, conn) -> None:
        acct_a = _account_id(conn, "acct_a")
        acct_b = _account_id(conn, "acct_b")
        id_a = _insert_backtest_run(conn, account_id=acct_a)
        id_b = _insert_backtest_run(conn, account_id=acct_b)
        ids = fetch_backtest_run_ids_for_account_ids(conn, (acct_a, acct_b))
        assert id_a in ids
        assert id_b in ids


class TestDeleteBacktestEquitySnapshotsByRunIds:
    def test_removes_snapshots_for_run(self, conn) -> None:
        acct_id = _account_id(conn)
        run_id = _insert_backtest_run(conn, account_id=acct_id)
        conn.execute(
            "INSERT INTO backtest_equity_snapshots (run_id, snapshot_time, cash, market_value, equity, realized_pnl, unrealized_pnl) VALUES (?,?,?,?,?,?,?)",
            (run_id, "2026-01-01T00:00:00Z", 0.0, 0.0, 1000.0, 0.0, 0.0),
        )
        conn.commit()
        delete_backtest_equity_snapshots_by_run_ids(conn, (run_id,))
        count = conn.execute(
            "SELECT COUNT(*) AS n FROM backtest_equity_snapshots WHERE run_id = ?", (run_id,)
        ).fetchone()["n"]
        assert count == 0


class TestDeleteBacktestTradesByRunIds:
    def test_removes_trades_for_run(self, conn) -> None:
        acct_id = _account_id(conn)
        run_id = _insert_backtest_run(conn, account_id=acct_id)
        conn.execute(
            "INSERT INTO backtest_trades (run_id, trade_time, ticker, side, qty, price) VALUES (?,?,?,?,?,?)",
            (run_id, "2026-01-01T10:00:00Z", "AAPL", "buy", 1.0, 100.0),
        )
        conn.commit()
        delete_backtest_trades_by_run_ids(conn, (run_id,))
        count = conn.execute("SELECT COUNT(*) AS n FROM backtest_trades WHERE run_id = ?", (run_id,)).fetchone()["n"]
        assert count == 0


class TestDeleteBacktestRunsByAccountIds:
    def test_removes_runs_for_account(self, conn) -> None:
        acct_id = _account_id(conn)
        _insert_backtest_run(conn, account_id=acct_id)
        delete_backtest_runs_by_account_ids(conn, (acct_id,))
        count = conn.execute("SELECT COUNT(*) AS n FROM backtest_runs WHERE account_id = ?", (acct_id,)).fetchone()[
            "n"
        ]
        assert count == 0

    def test_does_not_remove_runs_for_other_accounts(self, conn) -> None:
        acct_a = _account_id(conn, "acct_a")
        acct_b = _account_id(conn, "acct_b")
        _insert_backtest_run(conn, account_id=acct_a)
        _insert_backtest_run(conn, account_id=acct_b)
        delete_backtest_runs_by_account_ids(conn, (acct_a,))
        count = conn.execute("SELECT COUNT(*) AS n FROM backtest_runs WHERE account_id = ?", (acct_b,)).fetchone()["n"]
        assert count == 1


class TestDeleteEquitySnapshotsByAccountIds:
    def test_removes_snapshots_for_account(self, conn) -> None:
        acct_id = _account_id(conn)
        _insert_equity_snapshot(conn, account_id=acct_id)
        delete_equity_snapshots_by_account_ids(conn, (acct_id,))
        count = conn.execute("SELECT COUNT(*) AS n FROM equity_snapshots WHERE account_id = ?", (acct_id,)).fetchone()[
            "n"
        ]
        assert count == 0


class TestDeleteTradesByAccountIds:
    def test_removes_trades_for_account(self, conn) -> None:
        acct_id = _account_id(conn)
        _insert_trade(conn, account_id=acct_id)
        delete_trades_by_account_ids(conn, (acct_id,))
        count = conn.execute("SELECT COUNT(*) AS n FROM trades WHERE account_id = ?", (acct_id,)).fetchone()["n"]
        assert count == 0


class TestDeleteAccountsByIds:
    def test_removes_account(self, conn) -> None:
        acct_id = _account_id(conn)
        delete_accounts_by_ids(conn, (acct_id,))
        row = conn.execute("SELECT id FROM accounts WHERE id = ?", (acct_id,)).fetchone()
        assert row is None

    def test_does_not_remove_other_accounts(self, conn) -> None:
        acct_a = _account_id(conn, "acct_a")
        acct_b = _account_id(conn, "acct_b")
        delete_accounts_by_ids(conn, (acct_a,))
        row = conn.execute("SELECT id FROM accounts WHERE id = ?", (acct_b,)).fetchone()
        assert row is not None


class TestPromotionAndWalkForwardHelpers:
    def test_fetch_promotion_review_ids_returns_empty(self, conn) -> None:
        acct_id = _account_id(conn)
        assert fetch_promotion_review_ids_for_account_ids(conn, (acct_id,)) == ()

    def test_delete_promotion_reviews_noop_when_empty(self, conn) -> None:
        acct_id = _account_id(conn)
        delete_promotion_reviews_by_account_ids(conn, (acct_id,))

    def test_delete_promotion_review_events_noop_when_empty(self, conn) -> None:
        delete_promotion_review_events_by_review_ids(conn, ())

    def test_fetch_walk_forward_group_ids_returns_empty(self, conn) -> None:
        acct_id = _account_id(conn)
        assert fetch_walk_forward_group_ids_for_account_ids(conn, (acct_id,)) == ()

    def test_delete_walk_forward_groups_noop_when_empty(self, conn) -> None:
        acct_id = _account_id(conn)
        delete_walk_forward_groups_by_account_ids(conn, (acct_id,))

    def test_delete_walk_forward_group_runs_noop_when_empty(self, conn) -> None:
        delete_walk_forward_group_runs_by_group_ids(conn, ())
