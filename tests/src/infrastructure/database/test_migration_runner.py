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


def test_live_trading_enabled_defaults_to_disabled(migrated_conn: Any) -> None:
    # Live Trading Safety Guard: the migrated schema must never enable live
    # trading by default.
    columns = {row[1]: row for row in migrated_conn.execute("PRAGMA table_info(accounts)")}
    assert str(columns["live_trading_enabled"][4]) == "0"
