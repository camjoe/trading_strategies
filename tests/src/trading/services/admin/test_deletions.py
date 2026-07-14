from __future__ import annotations

import sqlite3

import pytest

from trading.services import admin as admin_service


class TestDeleteAccounts:
    def test_delete_accounts_dry_run_reports_counts_without_deleting(self, seeded_conn: sqlite3.Connection) -> None:
        counts = admin_service.delete_accounts(
            seeded_conn,
            account_names=["acct_a"],
            delete_all=False,
            dry_run=True,
        )

        assert counts == {
            "accounts": 1,
            "trades": 1,
            "orders": 1,
            "order_fills": 1,
            "equity_snapshots": 1,
            "backtest_runs": 1,
            "backtest_trades": 1,
            "backtest_equity_snapshots": 1,
            "walk_forward_groups": 1,
            "walk_forward_group_runs": 1,
            "promotion_reviews": 1,
            "promotion_review_events": 1,
            "risk_snapshots": 1,
            "risk_decisions": 1,
        }

        remaining = seeded_conn.execute("SELECT COUNT(*) AS n FROM accounts").fetchone()
        assert remaining is not None
        assert int(remaining["n"]) == 2

    def test_delete_accounts_removes_target_and_related_records_only(self, seeded_conn: sqlite3.Connection) -> None:
        counts = admin_service.delete_accounts(
            seeded_conn,
            account_names=["acct_a"],
            delete_all=False,
            dry_run=False,
        )

        assert counts["accounts"] == 1
        assert counts["trades"] == 1
        assert counts["backtest_runs"] == 1
        assert counts["promotion_reviews"] == 1
        assert counts["risk_snapshots"] == 1
        assert counts["risk_decisions"] == 1

        remaining_accounts = seeded_conn.execute("SELECT name FROM accounts ORDER BY name ASC").fetchall()
        assert [str(row["name"]) for row in remaining_accounts] == ["acct_b"]

        removed = {
            "trades": "SELECT COUNT(*) AS n FROM trades WHERE account_id = 1",
            "orders": "SELECT COUNT(*) AS n FROM orders WHERE account_id = 1",
            "order_fills": "SELECT COUNT(*) AS n FROM order_fills WHERE order_id = 501",
            "backtest_runs": "SELECT COUNT(*) AS n FROM backtest_runs WHERE account_id = 1",
            "promotion_reviews": "SELECT COUNT(*) AS n FROM promotion_reviews WHERE account_id = 1",
            "promotion_review_events": "SELECT COUNT(*) AS n FROM promotion_review_events WHERE review_id = 101",
            "walk_forward_groups": "SELECT COUNT(*) AS n FROM walk_forward_groups WHERE account_id = 1",
            "walk_forward_group_runs": "SELECT COUNT(*) AS n FROM walk_forward_group_runs WHERE run_id = 11",
            "risk_snapshots": "SELECT COUNT(*) AS n FROM risk_snapshots WHERE account_id = 1",
            "risk_decisions": "SELECT COUNT(*) AS n FROM risk_decisions WHERE account_id = 1",
        }
        for label, query in removed.items():
            row = seeded_conn.execute(query).fetchone()
            assert row is not None
            assert int(row["n"]) == 0, f"{label} rows for acct_a should be cascade-deleted"

    def test_delete_accounts_cascades_match_dry_run_counts(self, seeded_conn: sqlite3.Connection) -> None:
        """Cascade-backed deletion removes exactly the rows dry-run reported."""
        dry_counts = admin_service.delete_accounts(
            seeded_conn,
            account_names=["acct_a"],
            delete_all=False,
            dry_run=True,
        )

        counts = admin_service.delete_accounts(
            seeded_conn,
            account_names=["acct_a"],
            delete_all=False,
            dry_run=False,
        )

        assert counts == dry_counts
        assert seeded_conn.execute("PRAGMA foreign_key_check").fetchall() == []

        # The untouched account keeps its child rows across every cascaded table.
        surviving = {
            "orders": "SELECT COUNT(*) AS n FROM orders WHERE account_id = 2",
            "order_fills": "SELECT COUNT(*) AS n FROM order_fills WHERE order_id = 502",
            "backtest_trades": "SELECT COUNT(*) AS n FROM backtest_trades WHERE run_id = 22",
            "backtest_equity_snapshots": "SELECT COUNT(*) AS n FROM backtest_equity_snapshots WHERE run_id = 22",
            "promotion_review_events": "SELECT COUNT(*) AS n FROM promotion_review_events WHERE review_id = 202",
            "walk_forward_group_runs": "SELECT COUNT(*) AS n FROM walk_forward_group_runs WHERE group_id = 302",
            "risk_snapshots": "SELECT COUNT(*) AS n FROM risk_snapshots WHERE account_id = 2",
            "risk_decisions": "SELECT COUNT(*) AS n FROM risk_decisions WHERE account_id = 2",
        }
        for label, query in surviving.items():
            row = seeded_conn.execute(query).fetchone()
            assert row is not None
            assert int(row["n"]) == 1, f"{label} for acct_b should survive acct_a deletion"

    def test_delete_accounts_raises_for_missing_named_account(self, seeded_conn: sqlite3.Connection) -> None:
        with pytest.raises(ValueError, match="Accounts not found: missing"):
            admin_service.delete_accounts(
                seeded_conn,
                account_names=["missing"],
                delete_all=False,
                dry_run=True,
            )

    def test_delete_accounts_delete_all_with_no_accounts_returns_zeroes(self, empty_conn: sqlite3.Connection) -> None:
        counts = admin_service.delete_accounts(
            empty_conn,
            account_names=[],
            delete_all=True,
            dry_run=False,
        )

        assert counts == {
            "accounts": 0,
            "trades": 0,
            "orders": 0,
            "order_fills": 0,
            "equity_snapshots": 0,
            "backtest_runs": 0,
            "backtest_trades": 0,
            "backtest_equity_snapshots": 0,
            "walk_forward_groups": 0,
            "walk_forward_group_runs": 0,
            "promotion_reviews": 0,
            "promotion_review_events": 0,
            "risk_snapshots": 0,
            "risk_decisions": 0,
        }
