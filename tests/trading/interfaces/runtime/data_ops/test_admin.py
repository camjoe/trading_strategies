from argparse import Namespace
from datetime import datetime
from pathlib import Path

import pytest

from trading.database import db
from trading.interfaces.runtime.data_ops import admin
from trading.database.db_backend import SQLiteBackend, get_backend, set_backend


class FixedDateTime:
    @classmethod
    def now(cls) -> datetime:
        return datetime(2026, 3, 27, 8, 9, 10)


@pytest.fixture
def configured_backend(tmp_path: Path):
    original = get_backend()
    backend = SQLiteBackend(tmp_path / "paper_trading.db")
    set_backend(backend)
    try:
        yield backend
    finally:
        set_backend(original)


def _seed_admin_dataset() -> None:
    conn = db.ensure_db()
    try:
        conn.executescript(
            """
            INSERT INTO accounts (id, name, strategy, initial_cash, created_at)
            VALUES
                (1, 'acct_a', 'Trend', 1000, '2026-01-01T00:00:00Z'),
                (2, 'acct_b', 'Trend', 1500, '2026-01-01T00:00:00Z');

            INSERT INTO trades (account_id, ticker, side, qty, price, fee, trade_time, note)
            VALUES
                (1, 'SPY', 'buy', 1, 100, 0, '2026-01-02T00:00:00Z', ''),
                (2, 'QQQ', 'buy', 2, 200, 0, '2026-01-02T00:00:00Z', '');

            INSERT INTO equity_snapshots (account_id, snapshot_time, cash, market_value, equity, realized_pnl, unrealized_pnl)
            VALUES
                (1, '2026-01-02T00:00:00Z', 900, 100, 1000, 0, 0),
                (2, '2026-01-02T00:00:00Z', 1300, 200, 1500, 0, 0);

            INSERT INTO backtest_runs (id, account_id, strategy_name, run_name, start_date, end_date, created_at)
            VALUES
                (11, 1, 'Trend', 'run_a', '2025-01-01', '2025-06-01', '2026-01-03T00:00:00Z'),
                (22, 2, 'Trend', 'run_b', '2025-01-01', '2025-06-01', '2026-01-03T00:00:00Z');

            INSERT INTO backtest_trades (run_id, trade_time, ticker, side, qty, price, fee, slippage_bps, note)
            VALUES
                (11, '2025-01-10T00:00:00Z', 'SPY', 'buy', 1, 100, 0, 0, ''),
                (22, '2025-01-10T00:00:00Z', 'QQQ', 'buy', 1, 200, 0, 0, '');

            INSERT INTO backtest_equity_snapshots (run_id, snapshot_time, cash, market_value, equity, realized_pnl, unrealized_pnl)
            VALUES
                (11, '2025-01-10T00:00:00Z', 900, 100, 1000, 0, 0),
                (22, '2025-01-10T00:00:00Z', 1300, 200, 1500, 0, 0);

            INSERT INTO walk_forward_groups (
                id, grouping_key, account_id, strategy_name, run_name_prefix, start_date, end_date,
                test_months, step_months, window_count, average_return_pct, median_return_pct,
                best_return_pct, worst_return_pct, created_at
            )
            VALUES
                (301, 'acct_a_wf', 1, 'Trend', 'wf_a', '2025-01-01', '2025-06-01', 1, 1, 1, 2.0, 2.0, 2.0, 2.0, '2026-01-03T00:00:00Z'),
                (302, 'acct_b_wf', 2, 'Trend', 'wf_b', '2025-01-01', '2025-06-01', 1, 1, 1, 3.0, 3.0, 3.0, 3.0, '2026-01-03T00:00:00Z');

            INSERT INTO walk_forward_group_runs (group_id, run_id, window_index, window_start, window_end, total_return_pct)
            VALUES
                (301, 11, 1, '2025-01-01', '2025-06-01', 2.0),
                (302, 22, 1, '2025-01-01', '2025-06-01', 3.0);

            INSERT INTO promotion_reviews (
                id, account_id, account_name_snapshot, strategy_name, review_state,
                assessment_stage, assessment_status, ready_for_live, overall_confidence,
                live_trading_enabled_snapshot, promotion_assessment_version, evaluation_artifact_version,
                frozen_assessment_payload, frozen_evaluation_payload,
                requested_by, operator_summary_note, created_at, updated_at
            )
            VALUES
                (
                    101, 1, 'acct_a', 'Trend', 'requested',
                    'promotion_review', 'ready_for_review', 1, 0.75,
                    0, 'phase3.v1', 'phase2.v1',
                    '{"status":"ready_for_review"}', '{"basic":{"account_name":"acct_a"}}',
                    'alice', 'initial request', '2026-01-04T00:00:00Z', '2026-01-04T00:00:00Z'
                ),
                (
                    202, 2, 'acct_b', 'Trend', 'requested',
                    'promotion_review', 'ready_for_review', 1, 0.70,
                    0, 'phase3.v1', 'phase2.v1',
                    '{"status":"ready_for_review"}', '{"basic":{"account_name":"acct_b"}}',
                    'bob', 'initial request', '2026-01-04T00:00:00Z', '2026-01-04T00:00:00Z'
                );

            INSERT INTO promotion_review_events (
                review_id, event_seq, event_type, actor_type, actor_name,
                from_review_state, to_review_state, note, event_payload, created_at
            )
            VALUES
                (101, 1, 'requested', 'operator', 'alice', NULL, 'requested', 'initial request', '{}', '2026-01-04T00:00:00Z'),
                (202, 1, 'requested', 'operator', 'bob', NULL, 'requested', 'initial request', '{}', '2026-01-04T00:00:00Z');
            """
        )
        conn.commit()
    finally:
        conn.close()


class TestParseAccountNames:
    def test_parse_account_names_splits_deduplicates_and_strips(self) -> None:
        names = admin._parse_account_names(["acct_a, acct_b", "acct_b", " acct_c ", ""])

        assert names == ["acct_a", "acct_b", "acct_c"]


class TestBackupDatabase:
    def test_backup_database_raises_when_source_missing(self, configured_backend: SQLiteBackend) -> None:
        with pytest.raises(FileNotFoundError, match="Database file not found"):
            admin.backup_database()

    def test_backup_database_writes_timestamped_file_in_default_dir(
        self, configured_backend: SQLiteBackend, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db.ensure_db().close()
        monkeypatch.setattr(admin, "datetime", FixedDateTime)

        backup = admin.backup_database()

        assert backup.exists()
        assert backup.name.startswith("paper_trading_20260327_080910")
        assert backup.parent.name == "db_backups"

    def test_backup_database_accepts_explicit_file_destination(
        self, configured_backend: SQLiteBackend, tmp_path: Path
    ) -> None:
        db.ensure_db().close()
        destination = tmp_path / "custom" / "manual_backup.db"

        backup = admin.backup_database(str(destination))

        assert backup == destination
        assert backup.exists()


class TestDeleteAccounts:
    def test_delete_accounts_dry_run_reports_counts_without_deleting(self, configured_backend: SQLiteBackend) -> None:
        _seed_admin_dataset()

        conn = db.ensure_db()
        try:
            counts = admin.delete_accounts(
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

        conn = db.ensure_db()
        try:
            remaining = conn.execute("SELECT COUNT(*) AS n FROM accounts").fetchone()
            assert remaining is not None
            assert int(remaining["n"]) == 2
        finally:
            conn.close()

    def test_delete_accounts_removes_target_and_related_records_only(self, configured_backend: SQLiteBackend) -> None:
        _seed_admin_dataset()

        conn = db.ensure_db()
        try:
            counts = admin.delete_accounts(
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

        conn = db.ensure_db()
        try:
            remaining_accounts = conn.execute("SELECT name FROM accounts ORDER BY name ASC").fetchall()
            assert [str(row["name"]) for row in remaining_accounts] == ["acct_b"]

            trades = conn.execute("SELECT COUNT(*) AS n FROM trades WHERE account_id = 1").fetchone()
            runs = conn.execute("SELECT COUNT(*) AS n FROM backtest_runs WHERE account_id = 1").fetchone()
            reviews = conn.execute("SELECT COUNT(*) AS n FROM promotion_reviews WHERE account_id = 1").fetchone()
            events = conn.execute("SELECT COUNT(*) AS n FROM promotion_review_events WHERE review_id = 101").fetchone()
            walk_forward_groups = conn.execute("SELECT COUNT(*) AS n FROM walk_forward_groups WHERE account_id = 1").fetchone()
            walk_forward_group_runs = conn.execute("SELECT COUNT(*) AS n FROM walk_forward_group_runs WHERE run_id = 11").fetchone()
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
        _seed_admin_dataset()

        conn = db.ensure_db()
        try:
            with pytest.raises(ValueError, match="Accounts not found: missing"):
                admin.delete_accounts(
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
        db.ensure_db().close()

        conn = db.ensure_db()
        try:
            counts = admin.delete_accounts(
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


class TestCommandValidation:
    def test_cmd_delete_accounts_requires_yes_with_all(self) -> None:
        args = Namespace(
            accounts=[],
            all=True,
            yes=False,
            backup_before=False,
            backup_destination=None,
            dry_run=True,
        )

        with pytest.raises(ValueError, match="--all requires --yes"):
            admin._cmd_delete_accounts(args)

    def test_cmd_delete_accounts_requires_names_when_not_all(self) -> None:
        args = Namespace(
            accounts=[],
            all=False,
            yes=False,
            backup_before=False,
            backup_destination=None,
            dry_run=True,
        )

        with pytest.raises(ValueError, match="Provide at least one account name"):
            admin._cmd_delete_accounts(args)
