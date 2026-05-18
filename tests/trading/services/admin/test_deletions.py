import pytest

from trading.database.db_backend import SQLiteBackend
from trading.database.db_init import ensure_db
from trading.services import admin as admin_service
from tests.support.admin import seed_admin_dataset


class TestDeleteAccounts:
    def test_delete_accounts_dry_run_reports_counts_without_deleting(self, configured_backend: SQLiteBackend) -> None:
        seed_admin_dataset()

        conn = ensure_db()
        try:
            counts = admin_service.delete_accounts(
                conn,
                account_names=["acct_a"],
                delete_all=False,
                dry_run=True,
            )
        finally:
            conn.close()

        assert counts == {
            "accounts": 1,
            "trades": 1,
            "equity_snapshots": 1,
            "backtest_runs": 1,
            "backtest_trades": 1,
            "backtest_equity_snapshots": 1,
            "walk_forward_groups": 1,
            "walk_forward_group_runs": 1,
            "promotion_reviews": 1,
            "promotion_review_events": 1,
        }

        conn = ensure_db()
        try:
            remaining = conn.execute("SELECT COUNT(*) AS n FROM accounts").fetchone()
            assert remaining is not None
            assert int(remaining["n"]) == 2
        finally:
            conn.close()

    def test_delete_accounts_removes_target_and_related_records_only(self, configured_backend: SQLiteBackend) -> None:
        seed_admin_dataset()

        conn = ensure_db()
        try:
            counts = admin_service.delete_accounts(
                conn,
                account_names=["acct_a"],
                delete_all=False,
                dry_run=False,
            )
        finally:
            conn.close()

        assert counts["accounts"] == 1
        assert counts["trades"] == 1
        assert counts["backtest_runs"] == 1
        assert counts["promotion_reviews"] == 1

        conn = ensure_db()
        try:
            remaining_accounts = conn.execute("SELECT name FROM accounts ORDER BY name ASC").fetchall()
            assert [str(row["name"]) for row in remaining_accounts] == ["acct_b"]

            trades = conn.execute("SELECT COUNT(*) AS n FROM trades WHERE account_id = 1").fetchone()
            runs = conn.execute("SELECT COUNT(*) AS n FROM backtest_runs WHERE account_id = 1").fetchone()
            reviews = conn.execute("SELECT COUNT(*) AS n FROM promotion_reviews WHERE account_id = 1").fetchone()
            events = conn.execute("SELECT COUNT(*) AS n FROM promotion_review_events WHERE review_id = 101").fetchone()
            walk_forward_groups = conn.execute(
                "SELECT COUNT(*) AS n FROM walk_forward_groups WHERE account_id = 1"
            ).fetchone()
            walk_forward_group_runs = conn.execute(
                "SELECT COUNT(*) AS n FROM walk_forward_group_runs WHERE run_id = 11"
            ).fetchone()
            assert trades is not None
            assert runs is not None
            assert reviews is not None
            assert events is not None
            assert walk_forward_groups is not None
            assert walk_forward_group_runs is not None
            assert int(trades["n"]) == 0
            assert int(runs["n"]) == 0
            assert int(reviews["n"]) == 0
            assert int(events["n"]) == 0
            assert int(walk_forward_groups["n"]) == 0
            assert int(walk_forward_group_runs["n"]) == 0
        finally:
            conn.close()

    def test_delete_accounts_raises_for_missing_named_account(self, configured_backend: SQLiteBackend) -> None:
        seed_admin_dataset()

        conn = ensure_db()
        try:
            with pytest.raises(ValueError, match="Accounts not found: missing"):
                admin_service.delete_accounts(
                    conn,
                    account_names=["missing"],
                    delete_all=False,
                    dry_run=True,
                )
        finally:
            conn.close()

    def test_delete_accounts_delete_all_with_no_accounts_returns_zeroes(
        self, configured_backend: SQLiteBackend
    ) -> None:
        ensure_db().close()

        conn = ensure_db()
        try:
            counts = admin_service.delete_accounts(
                conn,
                account_names=[],
                delete_all=True,
                dry_run=False,
            )
        finally:
            conn.close()

        assert counts == {
            "accounts": 0,
            "trades": 0,
            "equity_snapshots": 0,
            "backtest_runs": 0,
            "backtest_trades": 0,
            "backtest_equity_snapshots": 0,
            "walk_forward_groups": 0,
            "walk_forward_group_runs": 0,
            "promotion_reviews": 0,
            "promotion_review_events": 0,
        }
