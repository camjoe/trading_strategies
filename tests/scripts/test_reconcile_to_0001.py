"""Tests for the one-time pre-baseline reconciliation script.

Transitional alongside `scripts/data_ops/reconcile_to_0001.py` — delete both when the Alembic
baseline transition is complete.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

import trading.interfaces.runtime.data_ops.admin as admin
from infrastructure.database import migration_runner
from infrastructure.database.backend import SQLiteBackend, get_backend, set_backend
from infrastructure.database.schema_compare import compare_schemas
from infrastructure.database.schema_version import read_database_revisions
from scripts.data_ops.manage_db_migrations import _cmd_baseline, _cmd_verify
from scripts.data_ops.reconcile_to_0001 import run_reconcile

# book_strategy_assignments with the legacy param_set_id column + FK (the shape aged/fresh
# probe databases carry). ALTER ADD COLUMN cannot reproduce the FK, so build it explicitly.
_LEGACY_BSA = """
CREATE TABLE book_strategy_assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL,
    strategy_id INTEGER NOT NULL,
    param_set_id INTEGER,
    effective_from TEXT NOT NULL,
    effective_to TEXT,
    is_incumbent INTEGER NOT NULL DEFAULT 1 CHECK (is_incumbent IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
    FOREIGN KEY (strategy_id) REFERENCES strategies(id),
    FOREIGN KEY (param_set_id) REFERENCES strategy_param_sets(id)
)
"""

_LEGACY_STRATEGY_PARAM_SETS = """
CREATE TABLE strategy_param_sets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_name TEXT NOT NULL,
    version TEXT NOT NULL,
    params_json TEXT NOT NULL,
    UNIQUE(strategy_name, version)
)
"""


@pytest.fixture
def injected_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    db_path = tmp_path / "paper_trading.db"
    monkeypatch.setattr(admin, "DB_BACKUPS_DIR", tmp_path / "backups")
    original = get_backend()
    set_backend(SQLiteBackend(db_path))
    try:
        yield db_path
    finally:
        set_backend(original)


def _seed_parents(conn: sqlite3.Connection) -> None:
    """Insert a minimal FK-valid account/book/strategy graph (ids all 1)."""
    ts = "2026-01-01T00:00:00Z"
    conn.execute(
        "INSERT INTO accounts (id, name, strategy, initial_cash, created_at) VALUES (1, 'a', 'trend', 1000, ?)",
        (ts,),
    )
    conn.execute(
        "INSERT INTO books (id, account_id, name, start_equity, current_cash, current_equity, created_at, updated_at) "
        "VALUES (1, 1, 'default', 1000, 1000, 1000, ?, ?)",
        (ts, ts),
    )
    conn.execute(
        "INSERT INTO strategies (id, strategy_key, primitive, params_json, style, created_at, updated_at) "
        "VALUES (1, 'k', 'p', '{}', 'trend', ?, ?)",
        (ts, ts),
    )


def _degrade_to_probe_shape(db_path: Path, *, with_param_set_fk: bool, orphans: tuple[str, ...]) -> None:
    """Turn a clean head database back into a pre-Alembic probe-shaped one."""
    conn = sqlite3.connect(db_path)
    conn.isolation_level = None
    conn.execute("PRAGMA foreign_keys = OFF")
    _seed_parents(conn)
    # Re-add the legacy strategy_param_sets store.
    conn.executescript(_LEGACY_STRATEGY_PARAM_SETS)
    # Replace clean book_strategy_assignments with the legacy shape (+ a data row to preserve).
    conn.execute("DROP TABLE book_strategy_assignments")
    conn.executescript(_LEGACY_BSA)
    if not with_param_set_fk:
        # Drop just the FK by rebuilding without it, keeping the column (aged-DB shape).
        conn.execute("ALTER TABLE book_strategy_assignments RENAME TO _tmp_bsa")
        conn.execute(_LEGACY_BSA.replace(", FOREIGN KEY (param_set_id) REFERENCES strategy_param_sets(id)", ""))
        conn.execute("DROP TABLE _tmp_bsa")
    conn.execute(
        "INSERT INTO book_strategy_assignments "
        "(book_id, strategy_id, effective_from, is_incumbent, created_at, updated_at) "
        "VALUES (1, 1, '2026-01-01T00:00:00Z', 1, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')"
    )
    for orphan in orphans:
        conn.execute(f"CREATE TABLE {orphan} (id INTEGER PRIMARY KEY, note TEXT)")
    # Un-version it: a reconciled database is pre-baseline.
    conn.execute("DROP TABLE IF EXISTS alembic_version")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.close()


def _make_probe_db(db_path: Path, *, with_param_set_fk: bool, orphans: tuple[str, ...] = ()) -> None:
    conn = sqlite3.connect(db_path)
    try:
        migration_runner.upgrade("head", connection=conn)
    finally:
        conn.close()
    _degrade_to_probe_shape(db_path, with_param_set_fk=with_param_set_fk, orphans=orphans)


def _baselines_clean(db_path: Path) -> bool:
    reference = migration_runner.build_reference_connection()
    conn = sqlite3.connect(db_path)
    try:
        return compare_schemas(reference, conn).matches
    finally:
        reference.close()
        conn.close()


@pytest.mark.parametrize("with_fk", [False, True])
def test_reconcile_makes_database_match_0001(injected_db: Path, with_fk: bool) -> None:
    _make_probe_db(injected_db, with_param_set_fk=with_fk, orphans=("broker_orders", "sleeve_orders"))
    assert not _baselines_clean(injected_db)  # diverges before reconciliation

    assert run_reconcile() == 0

    assert _baselines_clean(injected_db)
    # The full operator path then succeeds.
    assert _cmd_baseline(_args()) == 0
    assert _cmd_verify(_args()) == 0


def test_reconcile_preserves_assignment_rows(injected_db: Path) -> None:
    _make_probe_db(injected_db, with_param_set_fk=True)
    assert run_reconcile() == 0
    conn = sqlite3.connect(injected_db)
    try:
        assert conn.execute("SELECT COUNT(*) FROM book_strategy_assignments").fetchone()[0] == 1
        cols = {row[1] for row in conn.execute("PRAGMA table_info(book_strategy_assignments)")}
        assert "param_set_id" not in cols
    finally:
        conn.close()


def test_reconcile_backs_up_first(injected_db: Path, tmp_path: Path) -> None:
    _make_probe_db(injected_db, with_param_set_fk=False)
    assert run_reconcile() == 0
    assert list((tmp_path / "backups").glob("*.db"))


def test_reconcile_refuses_versioned_database(injected_db: Path) -> None:
    conn = sqlite3.connect(injected_db)
    try:
        migration_runner.upgrade("head", connection=conn)
    finally:
        conn.close()
    assert run_reconcile() == 1
    assert read_database_revisions(_connect(injected_db)) == ("0001",)


def test_reconcile_refuses_missing_database(injected_db: Path) -> None:
    assert run_reconcile() == 1


def _args() -> object:
    import argparse

    return argparse.Namespace()


def _connect(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(path)
