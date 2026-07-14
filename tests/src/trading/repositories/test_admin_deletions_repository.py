from __future__ import annotations

from trading.repositories.accounts import AccountRepository
from trading.repositories.admin_deletions import (
    count_child_rows_for_account_ids,
    fetch_row_count,
)
from trading.repositories.snapshots import EquitySnapshotRepository
from tests.support.repositories import insert_repository_account
from tests.support.strategies import ensure_strategy_id_for_label


def _account_id(conn, name: str = "admin_acct") -> int:
    return insert_repository_account(conn, name=name)


def _insert_backtest_run(conn, *, account_id: int, strategy_name: str = "trend") -> int:
    cursor = conn.execute(
        "INSERT INTO backtest_runs (account_id, strategy_id, start_date, end_date, created_at) VALUES (?,?,?,?,?)",
        (
            account_id,
            ensure_strategy_id_for_label(conn, strategy_name),
            "2026-01-01",
            "2026-06-01",
            "2026-01-01T00:00:00Z",
        ),
    )
    conn.commit()
    return cursor.lastrowid


def _insert_equity_snapshot(conn, *, account_id: int, snapshot_time: str = "2026-01-01T00:00:00Z") -> None:
    EquitySnapshotRepository(conn).insert(
        account_id=account_id,
        snapshot_time=snapshot_time,
        cash=1000.0,
        market_value=0.0,
        equity=1000.0,
        realized_pnl=0.0,
        unrealized_pnl=0.0,
    )


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


class TestCountChildRowsForAccountIds:
    def test_returns_zero_without_child_rows(self, conn) -> None:
        acct_id = _account_id(conn)
        assert count_child_rows_for_account_ids(conn, "backtest_trades", (acct_id,)) == 0

    def test_counts_rows_through_owning_parent(self, conn) -> None:
        acct_id = _account_id(conn)
        run_id = _insert_backtest_run(conn, account_id=acct_id)
        conn.execute(
            "INSERT INTO backtest_trades (run_id, trade_time, ticker, side, qty, price) VALUES (?,?,?,?,?,?)",
            (run_id, "2026-01-01T10:00:00Z", "AAPL", "buy", 1.0, 100.0),
        )
        conn.commit()
        assert count_child_rows_for_account_ids(conn, "backtest_trades", (acct_id,)) == 1

    def test_counts_book_keyed_snapshots(self, conn) -> None:
        acct_id = _account_id(conn)
        _insert_equity_snapshot(conn, account_id=acct_id)
        assert count_child_rows_for_account_ids(conn, "equity_snapshots", (acct_id,)) == 1

    def test_does_not_count_other_accounts(self, conn) -> None:
        acct_a = _account_id(conn, "acct_a")
        acct_b = _account_id(conn, "acct_b")
        _insert_equity_snapshot(conn, account_id=acct_b)
        assert count_child_rows_for_account_ids(conn, "equity_snapshots", (acct_a,)) == 0


class TestAccountRepositoryDeleteByIds:
    def test_removes_account_and_cascades_owned_rows(self, conn) -> None:
        acct_id = _account_id(conn)
        _insert_trade(conn, account_id=acct_id)
        run_id = _insert_backtest_run(conn, account_id=acct_id)

        AccountRepository(conn).delete_by_ids((acct_id,))

        assert conn.execute("SELECT id FROM accounts WHERE id = ?", (acct_id,)).fetchone() is None
        assert fetch_row_count(conn, "trades", "account_id", (acct_id,)) == 0
        assert conn.execute("SELECT id FROM backtest_runs WHERE id = ?", (run_id,)).fetchone() is None
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []

    def test_does_not_remove_other_accounts(self, conn) -> None:
        acct_a = _account_id(conn, "acct_a")
        acct_b = _account_id(conn, "acct_b")
        AccountRepository(conn).delete_by_ids((acct_a,))
        row = conn.execute("SELECT id FROM accounts WHERE id = ?", (acct_b,)).fetchone()
        assert row is not None

    def test_empty_ids_is_a_noop(self, conn) -> None:
        acct_id = _account_id(conn)
        AccountRepository(conn).delete_by_ids(())
        row = conn.execute("SELECT id FROM accounts WHERE id = ?", (acct_id,)).fetchone()
        assert row is not None
