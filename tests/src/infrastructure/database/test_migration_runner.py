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


def test_revision_0005_folds_option_settings_into_books(tmp_path: Path) -> None:
    conn = sqlite3.connect(tmp_path / "option_fold.db")
    conn.row_factory = sqlite3.Row
    try:
        migration_runner.upgrade("0004", connection=conn)
        conn.executescript(
            """
            INSERT INTO accounts (id, name, strategy, initial_cash, created_at, option_min_dte, option_type)
            VALUES
                (1, 'acct', 'Trend', 1000, '2026-01-01T00:00:00Z', 90, 'call'),
                -- 'both' is legal app vocabulary the retired 1:1 table's CHECK never allowed.
                (2, 'acct_both', 'Trend', 500, '2026-01-01T00:00:00Z', 30, 'both');
            INSERT INTO books (
                id, account_id, name, start_equity, current_cash, current_equity, created_at, updated_at
            )
            VALUES
                (1, 1, 'default', 1000, 1000, 1000, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z'),
                (2, 1, 'nosettings', 500, 500, 500, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z'),
                (3, 2, 'default', 500, 500, 500, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z');
            INSERT INTO book_option_settings (
                book_id, option_min_dte, option_type, max_premium_per_trade, created_at, updated_at
            )
            VALUES (1, 180, 'put', 700.0, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z');
            """
        )
        conn.commit()

        migration_runner.upgrade("0005", connection=conn)
        # Book 1 keeps its own settings row values; book 2 inherits the account's.
        rows = {
            int(r["id"]): r
            for r in conn.execute("SELECT id, option_min_dte, option_type, max_premium_per_trade FROM books")
        }
        assert (rows[1]["option_min_dte"], rows[1]["option_type"], rows[1]["max_premium_per_trade"]) == (
            180,
            "put",
            700.0,
        )
        assert (rows[2]["option_min_dte"], rows[2]["option_type"], rows[2]["max_premium_per_trade"]) == (
            90,
            "call",
            None,
        )
        # 'both' backfills intact — the books CHECK matches the app vocabulary.
        assert (rows[3]["option_min_dte"], rows[3]["option_type"]) == (30, "both")
        account_columns = {str(r[1]) for r in conn.execute("PRAGMA table_info(accounts)")}
        assert "option_min_dte" not in account_columns and "option_type" not in account_columns
        tables = {str(r[0]) for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "book_option_settings" not in tables
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []

        migration_runner.downgrade("0004", connection=conn)
        restored = conn.execute(
            "SELECT option_min_dte, option_type FROM book_option_settings WHERE book_id = 1"
        ).fetchone()
        assert (restored["option_min_dte"], restored["option_type"]) == (180, "put")
        # 'both' cannot round-trip into the 0001-shape CHECK; it maps to NULL.
        both_restored = conn.execute(
            "SELECT option_min_dte, option_type FROM book_option_settings WHERE book_id = 3"
        ).fetchone()
        assert (both_restored["option_min_dte"], both_restored["option_type"]) == (30, None)
        book_columns = {str(r[1]) for r in conn.execute("PRAGMA table_info(books)")}
        assert "option_min_dte" not in book_columns
        assert "risk_policy" in book_columns  # 0004 execution columns survive the rebuild
    finally:
        conn.close()


def test_revision_0006_drops_trades_table(tmp_path: Path) -> None:
    conn = sqlite3.connect(tmp_path / "trades_drop.db")
    conn.row_factory = sqlite3.Row
    try:
        migration_runner.upgrade("0005", connection=conn)
        assert conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0] == 0

        migration_runner.upgrade("0006", connection=conn)
        tables = {str(r[0]) for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "trades" not in tables
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []

        migration_runner.downgrade("0005", connection=conn)
        assert conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0] == 0
        indexes = {str(r[0]) for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
        assert "idx_trades_trade_time" in indexes
    finally:
        conn.close()


def test_revision_0007_backfills_promotion_strategy_fk(tmp_path: Path) -> None:
    conn = sqlite3.connect(tmp_path / "promotion_fk.db")
    conn.row_factory = sqlite3.Row
    try:
        migration_runner.upgrade("0006", connection=conn)
        conn.executescript(
            """
            INSERT INTO accounts (id, name, strategy, initial_cash, created_at)
            VALUES (1, 'acct', 'Trend', 1000, '2026-01-01T00:00:00Z');
            INSERT INTO strategies (
                id, strategy_key, primitive, params_json, style, status, enabled, created_at, updated_at
            )
            VALUES (7, 'trend', 'trend', '{}', 'trend', 'draft', 1, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z');
            INSERT INTO promotion_reviews (
                account_id, account_name_snapshot, strategy_name, review_state,
                assessment_stage, assessment_status, promotion_assessment_version,
                evaluation_artifact_version, frozen_assessment_payload,
                frozen_evaluation_payload, created_at, updated_at
            )
            VALUES
                (1, 'acct', 'Trend', 'requested', 'candidate', 'blocked', 'v1', 'v1', '{}', '{}',
                 '2026-01-02T00:00:00Z', '2026-01-02T00:00:00Z'),
                (1, 'acct', 'Ghost Strategy', 'closed', 'candidate', 'blocked', 'v1', 'v1', '{}', '{}',
                 '2026-01-03T00:00:00Z', '2026-01-03T00:00:00Z');
            """
        )
        conn.commit()

        migration_runner.upgrade("0007", connection=conn)
        rows = conn.execute(
            "SELECT strategy_name, strategy_id FROM promotion_reviews ORDER BY created_at ASC"
        ).fetchall()
        # Resolvable names get the FK (normalized match); unresolvable keep NULL.
        assert (rows[0]["strategy_name"], rows[0]["strategy_id"]) == ("Trend", 7)
        assert (rows[1]["strategy_name"], rows[1]["strategy_id"]) == ("Ghost Strategy", None)

        migration_runner.downgrade("0006", connection=conn)
        columns = {str(r[1]) for r in conn.execute("PRAGMA table_info(promotion_reviews)")}
        assert "strategy_id" not in columns
        assert conn.execute("SELECT COUNT(*) FROM promotion_reviews").fetchone()[0] == 2
        indexes = {str(r[0]) for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
        assert "idx_promotion_reviews_open_requested" in indexes
    finally:
        conn.close()


def test_revision_0008_universe_history_and_final_accounts_shape(tmp_path: Path) -> None:
    conn = sqlite3.connect(tmp_path / "final_shrink.db")
    conn.row_factory = sqlite3.Row
    try:
        migration_runner.upgrade("0007", connection=conn)
        conn.executescript(
            """
            INSERT INTO accounts (id, name, strategy, initial_cash, created_at, trade_universes, goal_min_return_pct)
            VALUES
                (1, 'acct_with', 'Trend', 1000, '2026-01-01T00:00:00Z', '["growth"]', 2.0),
                (2, 'acct_without', 'Trend', 500, '2026-01-01T00:00:00Z', NULL, NULL);
            INSERT INTO books (
                id, account_id, name, start_equity, current_cash, current_equity,
                trade_universes, created_at, updated_at
            )
            VALUES
                (1, 1, 'default', 1000, 1000, 1000, '["large_cap"]', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z'),
                (2, 1, 'second', 100, 100, 100, NULL, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z'),
                (3, 2, 'default', 500, 500, 500, NULL, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z');
            """
        )
        conn.commit()

        migration_runner.upgrade("0008", connection=conn)
        universes = {
            int(r["id"]): str(r["trade_universes"]) for r in conn.execute("SELECT id, trade_universes FROM books")
        }
        # Own value kept; account inherited; default backfilled.
        assert universes == {1: '["large_cap"]', 2: '["growth"]', 3: '["default"]'}
        history = conn.execute(
            "SELECT book_id, universes_json, effective_to FROM book_universe_history ORDER BY book_id"
        ).fetchall()
        assert [(r["book_id"], r["universes_json"], r["effective_to"]) for r in history] == [
            (1, '["large_cap"]', None),
            (2, '["growth"]', None),
            (3, '["default"]', None),
        ]
        account_columns = {str(r[1]) for r in conn.execute("PRAGMA table_info(accounts)")}
        assert account_columns == {
            "id",
            "name",
            "account_kind",
            "base_ccy",
            "initial_cash",
            "created_at",
            "updated_at",
            "benchmark_ticker",
            "descriptive_name",
            "broker_type",
            "broker_host",
            "broker_port",
            "broker_client_id",
            "live_trading_enabled",
        }
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []

        migration_runner.downgrade("0007", connection=conn)
        columns = {str(r[1]) for r in conn.execute("PRAGMA table_info(accounts)")}
        assert "strategy" in columns and "trade_universes" in columns
        tables = {str(r[0]) for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "book_universe_history" not in tables
        # Book universes survive the downgrade (nullable again, values kept).
        assert conn.execute("SELECT trade_universes FROM books WHERE id = 3").fetchone()[0] == '["default"]'
    finally:
        conn.close()


def test_revision_0014_drops_dead_rotation_settings_and_preserves_active_values(tmp_path: Path) -> None:
    conn = sqlite3.connect(tmp_path / "rotation_settings_drop.db")
    conn.row_factory = sqlite3.Row
    try:
        migration_runner.upgrade("0013", connection=conn)
        conn.executescript(
            """
            INSERT INTO accounts (id, name, initial_cash, created_at, updated_at)
            VALUES (1, 'acct', 1000, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z');
            INSERT INTO books (
                id, account_id, name, start_equity, current_cash, current_equity,
                trade_universes, created_at, updated_at
            )
            VALUES (
                1, 1, 'default', 1000, 1000, 1000,
                '["default"]', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z'
            );
            INSERT INTO book_rotation_settings (
                book_id, rotation_enabled, rotation_lookback_days, rotation_schedule,
                cooldown_days, created_at, updated_at
            )
            VALUES (
                1, 1, 45, '["trend"]', 10,
                '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z'
            );
            """
        )
        conn.commit()

        migration_runner.upgrade("0014", connection=conn)
        columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(book_rotation_settings)")}
        assert "rotation_schedule" in columns
        assert "rotation_mode" not in columns
        assert "regime_strategy_risk_on_id" not in columns
        assert "overlay_mode" not in columns
        row = conn.execute(
            "SELECT rotation_enabled, rotation_lookback_days, rotation_schedule, cooldown_days "
            "FROM book_rotation_settings WHERE book_id = 1"
        ).fetchone()
        assert tuple(row) == (1, 45, '["trend"]', 10)
        assert _fk_delete_action(conn, "book_rotation_settings", "book_id", "books") == "CASCADE"

        migration_runner.downgrade("0013", connection=conn)
        restored_columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(book_rotation_settings)")}
        assert {"rotation_mode", "regime_strategy_risk_on_id", "overlay_mode"} <= restored_columns
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        conn.close()


def test_revision_0014_refuses_populated_dead_rotation_setting(tmp_path: Path) -> None:
    conn = sqlite3.connect(tmp_path / "rotation_settings_guard.db")
    try:
        migration_runner.upgrade("0013", connection=conn)
        conn.executescript(
            """
            INSERT INTO accounts (id, name, initial_cash, created_at, updated_at)
            VALUES (1, 'acct', 1000, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z');
            INSERT INTO books (
                id, account_id, name, start_equity, current_cash, current_equity,
                trade_universes, created_at, updated_at
            )
            VALUES (
                1, 1, 'default', 1000, 1000, 1000,
                '["default"]', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z'
            );
            INSERT INTO book_rotation_settings (
                book_id, overlay_mode, created_at, updated_at
            )
            VALUES (1, 'legacy', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z');
            """
        )
        conn.commit()

        with pytest.raises(RuntimeError, match="refuses to discard populated"):
            migration_runner.upgrade("0014", connection=conn)
        columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(book_rotation_settings)")}
        assert "overlay_mode" in columns
        assert conn.execute("SELECT overlay_mode FROM book_rotation_settings").fetchone()[0] == "legacy"
    finally:
        conn.close()


def test_revision_0015_renames_book_strategy_history_and_indexes(tmp_path: Path) -> None:
    conn = sqlite3.connect(tmp_path / "strategy_history_rename.db")
    conn.row_factory = sqlite3.Row
    try:
        migration_runner.upgrade("0014", connection=conn)
        conn.executescript(
            """
            INSERT INTO accounts (id, name, initial_cash, created_at, updated_at)
            VALUES (1, 'acct', 1000, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z');
            INSERT INTO books (
                id, account_id, name, start_equity, current_cash, current_equity,
                trade_universes, created_at, updated_at
            )
            VALUES (
                1, 1, 'default', 1000, 1000, 1000,
                '["default"]', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z'
            );
            INSERT INTO strategies (
                id, strategy_key, primitive, params_json, style, created_at, updated_at
            )
            VALUES
                (1, 'trend', 'trend', '{}', 'trend', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z'),
                (2, 'meanrev', 'meanrev', '{}', 'mean_reversion', '2026-01-01T00:00:00Z',
                 '2026-01-01T00:00:00Z');
            INSERT INTO book_strategy_assignments (
                id, book_id, strategy_id, effective_from, effective_to, created_at, updated_at
            )
            VALUES
                (1, 1, 1, '2026-01-01T00:00:00Z', '2026-02-01T00:00:00Z',
                 '2026-01-01T00:00:00Z', '2026-02-01T00:00:00Z'),
                (2, 1, 2, '2026-02-01T00:00:00Z', NULL,
                 '2026-02-01T00:00:00Z', '2026-02-01T00:00:00Z');
            """
        )
        conn.commit()

        migration_runner.upgrade("0015", connection=conn)
        tables = _table_names(conn)
        assert "book_strategy_history" in tables
        assert "book_strategy_assignments" not in tables
        rows = conn.execute("SELECT id, strategy_id, effective_to FROM book_strategy_history ORDER BY id").fetchall()
        assert [tuple(row) for row in rows] == [
            (1, 1, "2026-02-01T00:00:00Z"),
            (2, 2, None),
        ]
        indexes = {str(row[0]) for row in conn.execute(_NAMED_INDEXES_QUERY)}
        assert {
            "idx_book_strategy_history_open_per_book",
            "idx_book_strategy_history_book_effective",
            "idx_book_strategy_history_strategy_effective",
        } <= indexes
        assert not {name for name in indexes if name.startswith("idx_book_assignments_")}
        assert _fk_delete_action(conn, "book_strategy_history", "book_id", "books") == "CASCADE"
        assert _fk_delete_action(conn, "book_strategy_history", "strategy_id", "strategies") == "NO ACTION"

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO book_strategy_history (
                    book_id, strategy_id, effective_from, created_at, updated_at
                )
                VALUES (1, 1, '2026-03-01T00:00:00Z', '2026-03-01T00:00:00Z', '2026-03-01T00:00:00Z')
                """
            )
        conn.rollback()

        migration_runner.downgrade("0014", connection=conn)
        tables = _table_names(conn)
        assert "book_strategy_assignments" in tables
        assert "book_strategy_history" not in tables
        assert conn.execute("SELECT COUNT(*) FROM book_strategy_assignments").fetchone()[0] == 2
        restored_indexes = {str(row[0]) for row in conn.execute(_NAMED_INDEXES_QUERY)}
        assert "idx_book_assignments_open_per_book" in restored_indexes
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        conn.close()


def test_live_trading_enabled_defaults_to_disabled(migrated_conn: Any) -> None:
    # Live Trading Safety Guard: the migrated schema must never enable live
    # trading by default.
    columns = {row[1]: row for row in migrated_conn.execute("PRAGMA table_info(accounts)")}
    assert str(columns["live_trading_enabled"][4]) == "0"
