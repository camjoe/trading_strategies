"""Tests for the migration lifecycle command (scripts.data_ops.manage_db_migrations)."""

from __future__ import annotations

import argparse
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

import trading.interfaces.runtime.data_ops.admin as admin
from infrastructure.database import migration_runner
from infrastructure.database.backend import SQLiteBackend, get_backend, set_backend
from infrastructure.database.schema_version import EXPECTED_HEAD_REVISION, read_database_revisions
from tests.support.db_schema import build_db_at_head
from scripts.data_ops.manage_db_migrations import (
    _cmd_baseline,
    _cmd_downgrade,
    _cmd_history,
    _cmd_status,
    _cmd_upgrade,
    _cmd_verify,
)


@pytest.fixture
def injected_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    db_path = tmp_path / "paper_trading.db"
    # Keep test backups out of the real local/db_backups directory.
    monkeypatch.setattr(admin, "DB_BACKUPS_DIR", tmp_path / "backups")
    original = get_backend()
    set_backend(SQLiteBackend(db_path))
    try:
        yield db_path
    finally:
        set_backend(original)


def _args(**kwargs: object) -> argparse.Namespace:
    return argparse.Namespace(**kwargs)


def _migrate_to_head(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        migration_runner.upgrade("head", connection=conn)
    finally:
        conn.close()


def _revisions(db_path: Path) -> tuple[str, ...]:
    conn = sqlite3.connect(db_path)
    try:
        return read_database_revisions(conn)
    finally:
        conn.close()


def _build_probe_database(db_path: Path) -> None:
    """Simulate a pre-Alembic database: current schema, no revision stamp.

    The probe system that originally built such databases is retired; its end
    state is exactly the head schema without an ``alembic_version`` table.
    """
    build_db_at_head(db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("DROP TABLE alembic_version")
        conn.commit()
    finally:
        conn.close()


def _backups(tmp_path: Path) -> list[Path]:
    backups_dir = tmp_path / "backups"
    return sorted(backups_dir.glob("*.db")) if backups_dir.exists() else []


# --- status ---------------------------------------------------------------


def test_status_missing_database(injected_db: Path) -> None:
    assert _cmd_status(_args()) == 1


def test_status_unversioned_empty(injected_db: Path) -> None:
    sqlite3.connect(injected_db).close()
    assert _cmd_status(_args()) == 1


def test_status_at_head(injected_db: Path) -> None:
    _migrate_to_head(injected_db)
    assert _cmd_status(_args()) == 0


def test_status_unversioned_populated(injected_db: Path) -> None:
    _build_probe_database(injected_db)
    assert _cmd_status(_args()) == 1


# --- upgrade ---------------------------------------------------------------


def test_upgrade_missing_database_refused(injected_db: Path) -> None:
    assert _cmd_upgrade(_args(revision="head")) == 1


def test_upgrade_at_head_is_noop_without_backup(injected_db: Path, tmp_path: Path) -> None:
    _migrate_to_head(injected_db)
    assert _cmd_upgrade(_args(revision="head")) == 0
    assert _backups(tmp_path) == []


def test_upgrade_refuses_unversioned_populated(injected_db: Path) -> None:
    _build_probe_database(injected_db)
    assert _cmd_upgrade(_args(revision="head")) == 1
    assert _revisions(injected_db) == ()


# --- downgrade -------------------------------------------------------------


def test_downgrade_to_base_backs_up_first(injected_db: Path, tmp_path: Path) -> None:
    _migrate_to_head(injected_db)
    assert _cmd_downgrade(_args(revision="base")) == 0
    assert _revisions(injected_db) == ()
    assert len(_backups(tmp_path)) == 1


def test_downgrade_missing_database_refused(injected_db: Path) -> None:
    assert _cmd_downgrade(_args(revision="base")) == 1


# --- baseline --------------------------------------------------------------


def test_baseline_adopts_probe_built_database(injected_db: Path) -> None:
    _build_probe_database(injected_db)
    assert _cmd_baseline(_args()) == 0
    assert _revisions(injected_db) == (EXPECTED_HEAD_REVISION,)
    # A baselined database then verifies clean.
    assert _cmd_verify(_args()) == 0


def test_baseline_preserves_user_data(injected_db: Path) -> None:
    _build_probe_database(injected_db)
    conn = sqlite3.connect(injected_db)
    conn.execute(
        "INSERT INTO accounts (name, strategy, initial_cash, created_at, descriptive_name) "
        "VALUES ('acct', 'demo', 1000.0, '2026-07-14T00:00:00', 'acct')"
    )
    conn.commit()
    conn.close()

    assert _cmd_baseline(_args()) == 0
    conn = sqlite3.connect(injected_db)
    try:
        count = conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
        assert count == 1
    finally:
        conn.close()


def test_baseline_mismatch_reports_and_does_not_stamp(injected_db: Path) -> None:
    _build_probe_database(injected_db)
    conn = sqlite3.connect(injected_db)
    conn.execute("DROP INDEX idx_trades_trade_time")
    conn.execute("CREATE TABLE rogue_table (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

    assert _cmd_baseline(_args()) == 1
    assert _revisions(injected_db) == ()


def test_baseline_refuses_empty_database(injected_db: Path) -> None:
    sqlite3.connect(injected_db).close()
    assert _cmd_baseline(_args()) == 1
    assert _revisions(injected_db) == ()


def test_baseline_refuses_already_versioned_database(injected_db: Path) -> None:
    _migrate_to_head(injected_db)
    assert _cmd_baseline(_args()) == 1


# --- verify ----------------------------------------------------------------


def test_verify_clean_at_head(injected_db: Path) -> None:
    _migrate_to_head(injected_db)
    assert _cmd_verify(_args()) == 0


def test_verify_detects_manual_drift(injected_db: Path) -> None:
    _migrate_to_head(injected_db)
    conn = sqlite3.connect(injected_db)
    conn.execute("DROP INDEX idx_trades_trade_time")
    conn.commit()
    conn.close()
    # alembic_version still says head, but the schema has drifted.
    assert _revisions(injected_db) == (EXPECTED_HEAD_REVISION,)
    assert _cmd_verify(_args()) == 1


def test_verify_refuses_unversioned_database(injected_db: Path) -> None:
    _build_probe_database(injected_db)
    assert _cmd_verify(_args()) == 1


# --- history ---------------------------------------------------------------


def test_history_lists_chain(injected_db: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _migrate_to_head(injected_db)
    assert _cmd_history(_args()) == 0
    output = capsys.readouterr().out
    assert "base -> 0001" in output
    assert "(current)" in output
