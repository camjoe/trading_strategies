"""Tests for the fresh-schema setup command (scripts.data_ops.setup_db_schema)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from infrastructure.database.backend import SQLiteBackend, get_backend, set_backend
from infrastructure.database.schema_version import EXPECTED_HEAD_REVISION, read_database_revisions
from scripts.data_ops.setup_db_schema import run_setup


@pytest.fixture
def injected_db(tmp_path: Path) -> Iterator[Path]:
    db_path = tmp_path / "paper_trading.db"
    original = get_backend()
    set_backend(SQLiteBackend(db_path))
    try:
        yield db_path
    finally:
        set_backend(original)


def _revisions(db_path: Path) -> tuple[str, ...]:
    import sqlite3

    conn = sqlite3.connect(db_path)
    try:
        return read_database_revisions(conn)
    finally:
        conn.close()


def test_setup_creates_missing_database_at_head(injected_db: Path) -> None:
    assert run_setup() == 0
    assert injected_db.exists()
    assert _revisions(injected_db) == (EXPECTED_HEAD_REVISION,)


def test_setup_refuses_already_versioned_database(injected_db: Path) -> None:
    assert run_setup() == 0
    # Second run must reject rather than reapply or restamp.
    assert run_setup() == 1
    assert _revisions(injected_db) == (EXPECTED_HEAD_REVISION,)


def test_setup_refuses_populated_unversioned_database(injected_db: Path) -> None:
    import sqlite3

    conn = sqlite3.connect(injected_db)
    conn.execute("CREATE TABLE accounts (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

    assert run_setup() == 1
    # The database must be left unversioned and unchanged.
    assert _revisions(injected_db) == ()


def test_setup_does_not_seed_application_data(injected_db: Path) -> None:
    import sqlite3

    assert run_setup() == 0
    conn = sqlite3.connect(injected_db)
    try:
        for table in ("accounts", "strategies", "global_settings"):
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            assert count == 0
    finally:
        conn.close()
