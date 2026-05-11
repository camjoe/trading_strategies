"""
Smoke tests for tests/support/seed_db.py.

These tests verify that ``seed_session_db`` correctly populates the database
with the expected canonical dataset.  They live here — next to the seed module
— rather than in domain-specific test files, because they're testing the
test-infrastructure fixture, not any production behaviour.
"""
from __future__ import annotations

from tests.support.seed_db import (
    ACCT_LOCAL,
    ACCT_MOMENTUM,
    ACCT_TREND,
    BACKTEST_RUN_NAME,
    PROMOTION_STRATEGY,
    SNAPSHOT_T1,
    SNAPSHOT_T2,
    SNAPSHOT_T3,
)


class TestSeededAccounts:
    def test_all_named_accounts_are_present(self, seeded_conn) -> None:
        names = {
            row["name"]
            for row in seeded_conn.execute("SELECT name FROM accounts").fetchall()
        }
        assert {ACCT_TREND, ACCT_MOMENTUM, ACCT_LOCAL}.issubset(names)

    def test_account_kinds_are_correct(self, seeded_conn) -> None:
        rows = {
            row["name"]: row["account_kind"]
            for row in seeded_conn.execute(
                "SELECT name, account_kind FROM accounts WHERE name IN (?, ?, ?)",
                (ACCT_TREND, ACCT_MOMENTUM, ACCT_LOCAL),
            ).fetchall()
        }
        assert rows[ACCT_TREND] == "managed"
        assert rows[ACCT_MOMENTUM] == "managed"
        assert rows[ACCT_LOCAL] == "local"


class TestSeededTrades:
    def test_trend_account_has_three_trades(self, seeded_conn) -> None:
        acct_id = seeded_conn.execute(
            "SELECT id FROM accounts WHERE name = ?", (ACCT_TREND,)
        ).fetchone()["id"]
        count = seeded_conn.execute(
            "SELECT COUNT(*) AS n FROM trades WHERE account_id = ?", (acct_id,)
        ).fetchone()["n"]
        assert count == 3


class TestSeededSnapshots:
    def test_trend_account_has_three_snapshots(self, seeded_conn) -> None:
        acct_id = seeded_conn.execute(
            "SELECT id FROM accounts WHERE name = ?", (ACCT_TREND,)
        ).fetchone()["id"]
        times = {
            row["snapshot_time"]
            for row in seeded_conn.execute(
                "SELECT snapshot_time FROM equity_snapshots WHERE account_id = ?",
                (acct_id,),
            ).fetchall()
        }
        assert {SNAPSHOT_T1, SNAPSHOT_T2, SNAPSHOT_T3}.issubset(times)


class TestSeededGlobalSettings:
    def test_global_settings_row_exists(self, seeded_conn) -> None:
        row = seeded_conn.execute("SELECT id FROM global_settings WHERE id = 1").fetchone()
        assert row is not None


class TestSeededBacktestRun:
    def test_backtest_run_linked_to_trend_account(self, seeded_conn) -> None:
        acct_id = seeded_conn.execute(
            "SELECT id FROM accounts WHERE name = ?", (ACCT_TREND,)
        ).fetchone()["id"]
        row = seeded_conn.execute(
            "SELECT run_name FROM backtest_runs WHERE account_id = ? AND run_name = ?",
            (acct_id, BACKTEST_RUN_NAME),
        ).fetchone()
        assert row is not None


class TestSeededPromotionReview:
    def test_promotion_review_exists_for_trend_account(self, seeded_conn) -> None:
        row = seeded_conn.execute(
            "SELECT review_state FROM promotion_reviews WHERE account_name_snapshot = ? AND strategy_name = ?",
            (ACCT_TREND, PROMOTION_STRATEGY),
        ).fetchone()
        assert row is not None
        assert row["review_state"] == "requested"
