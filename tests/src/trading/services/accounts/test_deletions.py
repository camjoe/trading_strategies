from __future__ import annotations

import sqlite3

import pytest

from trading.services import accounts as accounts_service


class TestPreviewAccountDeletion:
    def test_reports_compact_cascade_impact_without_deleting(
        self,
        deletion_seeded_conn: sqlite3.Connection,
    ) -> None:
        preview = accounts_service.preview_account_deletion(deletion_seeded_conn, "acct_a")

        assert preview.account_name == "acct_a"
        assert preview.descriptive_name == "acct_a"
        assert preview.strategy == "Trend"
        assert deletion_seeded_conn.execute("SELECT id FROM accounts WHERE name = 'acct_a'").fetchone() is not None

    def test_raises_for_missing_account(self, deletion_seeded_conn: sqlite3.Connection) -> None:
        with pytest.raises(ValueError, match="Account 'missing' not found"):
            accounts_service.preview_account_deletion(deletion_seeded_conn, "missing")


class TestDeleteAccount:
    def test_deletes_one_account_and_all_related_rows(
        self,
        deletion_seeded_conn: sqlite3.Connection,
    ) -> None:
        deleted = accounts_service.delete_account(deletion_seeded_conn, "acct_a")

        assert deleted.name == "acct_a"
        remaining_accounts = deletion_seeded_conn.execute("SELECT name FROM accounts ORDER BY name ASC").fetchall()
        assert [str(row["name"]) for row in remaining_accounts] == ["acct_b"]

        removed = {
            "books": "SELECT COUNT(*) AS n FROM books WHERE account_id = 1",
            "equity_snapshots": "SELECT COUNT(*) AS n FROM equity_snapshots WHERE book_id = 1",
            "daily_metrics": "SELECT COUNT(*) AS n FROM daily_metrics WHERE book_id = 1",
            "rotation_decisions": "SELECT COUNT(*) AS n FROM rotation_decisions WHERE book_id = 1",
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
            row = deletion_seeded_conn.execute(query).fetchone()
            assert row is not None
            assert int(row["n"]) == 0, f"{label} rows for acct_a should be cascade-deleted"

        assert deletion_seeded_conn.execute("PRAGMA foreign_key_check").fetchall() == []

    def test_raises_for_missing_account(self, deletion_seeded_conn: sqlite3.Connection) -> None:
        with pytest.raises(ValueError, match="Account 'missing' not found"):
            accounts_service.delete_account(deletion_seeded_conn, "missing")

    def test_rejects_empty_account_name(self, deletion_seeded_conn: sqlite3.Connection) -> None:
        with pytest.raises(ValueError, match="account_name cannot be empty"):
            accounts_service.delete_account(deletion_seeded_conn, "  ")
