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
from scripts.data_ops.manage_db_migrations import (
    _cmd_downgrade,
    _cmd_history,
    _cmd_status,
    _cmd_upgrade,
)
from tests.support.db_schema import build_db_at_head


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


def _unversioned_populated_db(db_path: Path) -> None:
    """A populated database with no revision stamp (the pre-transition shape)."""
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
    _unversioned_populated_db(injected_db)
    assert _cmd_status(_args()) == 1


# --- upgrade ---------------------------------------------------------------


def test_upgrade_creates_missing_database_at_head(injected_db: Path, tmp_path: Path) -> None:
    assert _cmd_upgrade(_args(revision="head")) == 0
    assert _revisions(injected_db) == (EXPECTED_HEAD_REVISION,)
    # Fresh setup: no backup taken and no application data seeded.
    assert _backups(tmp_path) == []
    conn = sqlite3.connect(injected_db)
    try:
        assert conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 0
    finally:
        conn.close()


def test_upgrade_at_head_is_noop_without_backup(injected_db: Path, tmp_path: Path) -> None:
    _migrate_to_head(injected_db)
    assert _cmd_upgrade(_args(revision="head")) == 0
    assert _backups(tmp_path) == []


def test_upgrade_refuses_unversioned_populated(injected_db: Path) -> None:
    _unversioned_populated_db(injected_db)
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


# --- history ---------------------------------------------------------------


def test_history_lists_chain(injected_db: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _migrate_to_head(injected_db)
    assert _cmd_history(_args()) == 0
    output = capsys.readouterr().out
    assert "base -> 0001" in output
    assert "(current)" in output
