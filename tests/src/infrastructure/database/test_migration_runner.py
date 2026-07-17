"""Tests for the Alembic migration runner and revision 0001."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from infrastructure.database import migration_runner
from infrastructure.database.backend import SQLiteBackend, get_backend, set_backend
from infrastructure.database.schema_version import EXPECTED_HEAD_REVISION, read_database_revisions

_APPLICATION_TABLES_QUERY = (
    "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' AND name != 'alembic_version'"
)
_NAMED_INDEXES_QUERY = "SELECT name FROM sqlite_master WHERE type = 'index' AND name LIKE 'idx_%'"


@pytest.fixture
def migrated_conn(tmp_path: Path) -> Any:
    conn = sqlite3.connect(tmp_path / "via_alembic.db")
    conn.row_factory = sqlite3.Row
    migration_runner.upgrade("head", connection=conn)
    try:
        yield conn
    finally:
        conn.close()


def _table_names(conn: Any) -> set[str]:
    return {str(row[0]) for row in conn.execute(_APPLICATION_TABLES_QUERY)}


def _structure(conn: Any) -> dict[str, Any]:
    """Normalized structure: per-table column/FK sets plus named index names."""
    structure: dict[str, Any] = {}
    for table in sorted(_table_names(conn)):
        columns = conn.execute(f"PRAGMA table_info({table})").fetchall()
        foreign_keys = conn.execute(f"PRAGMA foreign_key_list({table})").fetchall()
        structure[table] = {
            "columns": {(row[1], row[2], row[3], row[4], row[5]) for row in columns},
            "foreign_keys": {(row[2], row[3], row[4], row[6]) for row in foreign_keys},
        }
    structure["__indexes__"] = {str(row[0]) for row in conn.execute(_NAMED_INDEXES_QUERY)}
    return structure


def test_repository_head_matches_expected_constant() -> None:
    assert migration_runner.repository_head() == EXPECTED_HEAD_REVISION


def test_upgrade_records_head_revision(migrated_conn: Any) -> None:
    assert read_database_revisions(migrated_conn) == (EXPECTED_HEAD_REVISION,)


def test_build_reference_connection_materializes_head(tmp_path: Path) -> None:
    reference = migration_runner.build_reference_connection()
    try:
        assert read_database_revisions(reference) == (EXPECTED_HEAD_REVISION,)
        assert "accounts" in _table_names(reference)
    finally:
        reference.close()


def test_upgrade_at_head_is_a_noop(migrated_conn: Any) -> None:
    before = _structure(migrated_conn)
    migration_runner.upgrade("head", connection=migrated_conn)
    assert _structure(migrated_conn) == before
    assert read_database_revisions(migrated_conn) == (EXPECTED_HEAD_REVISION,)


def test_downgrade_to_base_drops_all_tables(migrated_conn: Any) -> None:
    migration_runner.downgrade("base", connection=migrated_conn)
    assert _table_names(migrated_conn) == set()
    assert read_database_revisions(migrated_conn) == ()


def test_downgrade_then_upgrade_round_trip(migrated_conn: Any) -> None:
    expected = _structure(migrated_conn)
    migration_runner.downgrade("base", connection=migrated_conn)
    migration_runner.upgrade("head", connection=migrated_conn)
    assert _structure(migrated_conn) == expected


def test_runner_uses_active_backend_when_no_connection_given(tmp_path: Path) -> None:
    db_path = tmp_path / "backend_owned.db"
    original = get_backend()
    set_backend(SQLiteBackend(db_path))
    try:
        migration_runner.upgrade("head")
    finally:
        set_backend(original)

    conn = sqlite3.connect(db_path)
    try:
        assert read_database_revisions(conn) == (EXPECTED_HEAD_REVISION,)
        assert "accounts" in _table_names(conn)
    finally:
        conn.close()


def test_read_database_revisions_empty_for_unversioned(tmp_path: Path) -> None:
    conn = sqlite3.connect(tmp_path / "unversioned.db")
    try:
        assert read_database_revisions(conn) == ()
    finally:
        conn.close()


def _fk_delete_action(conn: Any, table: str, column: str, references: str) -> str | None:
    for row in conn.execute(f"PRAGMA foreign_key_list({table})").fetchall():
        if str(row[3]) == column and str(row[2]) == references:
            return str(row[6]).upper()
    return None


def test_child_owned_foreign_keys_cascade(migrated_conn: Any) -> None:
    assert _fk_delete_action(migrated_conn, "order_fills", "order_id", "orders") == "CASCADE"
    assert _fk_delete_action(migrated_conn, "backtest_trades", "run_id", "backtest_runs") == "CASCADE"
    assert _fk_delete_action(migrated_conn, "backtest_equity_snapshots", "run_id", "backtest_runs") == "CASCADE"
    assert _fk_delete_action(migrated_conn, "promotion_review_events", "review_id", "promotion_reviews") == "CASCADE"
    assert _fk_delete_action(migrated_conn, "walk_forward_group_runs", "group_id", "walk_forward_groups") == "CASCADE"
    assert _fk_delete_action(migrated_conn, "walk_forward_group_runs", "run_id", "backtest_runs") == "NO ACTION"


def test_account_owned_foreign_keys_cascade(migrated_conn: Any) -> None:
    for table in (
        "trades",
        "orders",
        "backtest_runs",
        "walk_forward_groups",
        "promotion_reviews",
        "risk_snapshots",
        "risk_decisions",
        "books",
    ):
        assert _fk_delete_action(migrated_conn, table, "account_id", "accounts") == "CASCADE", table
    # Standalone book deletion keeps account-level decision history.
    assert _fk_delete_action(migrated_conn, "risk_decisions", "book_id", "books") == "SET NULL"
    # Book-owned history rides the accounts -> books cascade (revision 0002);
    # RESTRICT here blocked account deletion for accounts with rotation history.
    assert _fk_delete_action(migrated_conn, "rotation_decisions", "book_id", "books") == "CASCADE"


def test_revision_0002_rebuild_preserves_rotation_rows(tmp_path: Path) -> None:
    conn = sqlite3.connect(tmp_path / "rebuild.db")
    conn.row_factory = sqlite3.Row
    try:
        migration_runner.upgrade("0001", connection=conn)
        conn.executescript(
            """
            INSERT INTO accounts (id, name, strategy, initial_cash, created_at)
            VALUES (1, 'acct', 'Trend', 1000, '2026-01-01T00:00:00Z');
            INSERT INTO books (
                id, account_id, name, start_equity, current_cash, current_equity,
                created_at, updated_at
            )
            VALUES (1, 1, 'default', 1000, 1000, 1000, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z');
            INSERT INTO rotation_decisions (
                book_id, decision_time, rotation_action, score_components_json,
                gate_results_json, decision_reason, created_at
            )
            VALUES (1, '2026-01-02T00:00:00Z', 'hold', '{}', '{}', 'seeded', '2026-01-02T00:00:00Z');
            """
        )
        conn.commit()

        migration_runner.upgrade("head", connection=conn)
        row = conn.execute("SELECT book_id, rotation_action, decision_reason FROM rotation_decisions").fetchone()
        assert (row["book_id"], row["rotation_action"], row["decision_reason"]) == (1, "hold", "seeded")
        assert _fk_delete_action(conn, "rotation_decisions", "book_id", "books") == "CASCADE"

        migration_runner.downgrade("0001", connection=conn)
        assert conn.execute("SELECT COUNT(*) FROM rotation_decisions").fetchone()[0] == 1
        assert _fk_delete_action(conn, "rotation_decisions", "book_id", "books") == "RESTRICT"
    finally:
        conn.close()


def test_revision_0003_drops_rotation_columns_and_preserves_accounts(tmp_path: Path) -> None:
    conn = sqlite3.connect(tmp_path / "rotation_drop.db")
    conn.row_factory = sqlite3.Row
    try:
        migration_runner.upgrade("0002", connection=conn)
        conn.executescript(
            """
            INSERT INTO accounts (
                id, name, strategy, initial_cash, created_at,
                rotation_enabled, rotation_schedule, rotation_active_strategy,
                stop_loss_pct, trade_universes, broker_type
            )
            VALUES (
                1, 'acct', 'Trend', 1000, '2026-01-01T00:00:00Z',
                1, '["trend","breakout"]', 'breakout',
                4.5, '["large_cap"]', 'paper'
            );
            INSERT INTO books (
                id, account_id, name, start_equity, current_cash, current_equity,
                created_at, updated_at
            )
            VALUES (1, 1, 'default', 1000, 1000, 1000, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z');
            """
        )
        conn.commit()

        migration_runner.upgrade("0003", connection=conn)
        columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(accounts)")}
        assert not {name for name in columns if name.startswith("rotation_")}
        row = conn.execute(
            "SELECT name, strategy, initial_cash, stop_loss_pct, trade_universes, broker_type FROM accounts"
        ).fetchone()
        assert (row["name"], row["strategy"], row["initial_cash"]) == ("acct", "Trend", 1000)
        assert (row["stop_loss_pct"], row["trade_universes"], row["broker_type"]) == (4.5, '["large_cap"]', "paper")
        # The child FK survives the parent rebuild.
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []

        migration_runner.downgrade("0002", connection=conn)
        restored = {str(r[1]): r for r in conn.execute("PRAGMA table_info(accounts)")}
        assert "rotation_enabled" in restored and "rotation_active_strategy" in restored
        # Downgrade restores shape only: rotation values come back as defaults.
        row = conn.execute("SELECT rotation_enabled, rotation_schedule, stop_loss_pct FROM accounts").fetchone()
        assert (row["rotation_enabled"], row["rotation_schedule"], row["stop_loss_pct"]) == (0, None, 4.5)
    finally:
        conn.close()


def test_revision_0004_folds_execution_settings_into_books(tmp_path: Path) -> None:
    conn = sqlite3.connect(tmp_path / "execution_fold.db")
    conn.row_factory = sqlite3.Row
    try:
        migration_runner.upgrade("0003", connection=conn)
        conn.executescript(
            """
            INSERT INTO accounts (id, name, strategy, initial_cash, created_at, risk_policy, stop_loss_pct)
            VALUES (1, 'acct', 'Trend', 1000, '2026-01-01T00:00:00Z', 'fixed_stop', 7.5);
            INSERT INTO books (
                id, account_id, name, start_equity, current_cash, current_equity, created_at, updated_at
            )
            VALUES
                (1, 1, 'default', 1000, 1000, 1000, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z'),
                (2, 1, 'nosettings', 500, 500, 500, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z');
            INSERT INTO book_execution_settings (
                book_id, risk_policy, stop_loss_pct, max_trades_per_run, created_at, updated_at
            )
            VALUES (1, 'stop_and_target', 4.0, 3, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z');
            """
        )
        conn.commit()

        migration_runner.upgrade("0004", connection=conn)
        # Book 1 keeps its own settings row values; book 2 inherits the account's.
        rows = {
            int(r["id"]): r
            for r in conn.execute("SELECT id, risk_policy, stop_loss_pct, max_trades_per_run FROM books")
        }
        assert (rows[1]["risk_policy"], rows[1]["stop_loss_pct"], rows[1]["max_trades_per_run"]) == (
            "stop_and_target",
            4.0,
            3,
        )
        assert (rows[2]["risk_policy"], rows[2]["stop_loss_pct"], rows[2]["max_trades_per_run"]) == (
            "fixed_stop",
            7.5,
            None,
        )
        account_columns = {str(r[1]) for r in conn.execute("PRAGMA table_info(accounts)")}
        assert "risk_policy" not in account_columns and "stop_loss_pct" not in account_columns
        tables = {str(r[0]) for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "book_execution_settings" not in tables
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []

        migration_runner.downgrade("0003", connection=conn)
        restored = conn.execute(
            "SELECT risk_policy, stop_loss_pct FROM book_execution_settings WHERE book_id = 1"
        ).fetchone()
        assert (restored["risk_policy"], restored["stop_loss_pct"]) == ("stop_and_target", 4.0)
        book_columns = {str(r[1]) for r in conn.execute("PRAGMA table_info(books)")}
        assert "risk_policy" not in book_columns
    finally:
        conn.close()


def test_live_trading_enabled_defaults_to_disabled(migrated_conn: Any) -> None:
    # Live Trading Safety Guard: the migrated schema must never enable live
    # trading by default.
    columns = {row[1]: row for row in migrated_conn.execute("PRAGMA table_info(accounts)")}
    assert str(columns["live_trading_enabled"][4]) == "0"
