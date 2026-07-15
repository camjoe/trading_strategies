"""Runtime connection gate: ensure_db() verifies the Alembic revision.

Covers the runtime states required by docs/numbered-database-migration-plan.md:
missing/empty, unversioned-populated, behind, at-head, ahead, and branched.
Runtime never applies or downgrades migrations — every bad state must fail
before application queries run, with the remediation command in the message.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from infrastructure.database.backend import SQLiteBackend, get_backend, set_backend
from infrastructure.database.init import SchemaVersionError, db_session, ensure_db
from tests.support.db_schema import build_db_at_head


@pytest.fixture
def db_path(tmp_path: Path) -> Iterator[Path]:
    path = tmp_path / "paper_trading.db"
    original = get_backend()
    set_backend(SQLiteBackend(path))
    try:
        yield path
    finally:
        set_backend(original)


def _set_version(path: Path, *versions: str) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute("DELETE FROM alembic_version")
        for version in versions:
            conn.execute("INSERT INTO alembic_version (version_num) VALUES (?)", (version,))
        conn.commit()
    finally:
        conn.close()


def test_at_head_database_connects(db_path: Path) -> None:
    build_db_at_head(db_path)
    conn = ensure_db()
    try:
        assert conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 0
    finally:
        conn.close()


def test_missing_or_empty_database_is_rejected_with_setup_command(db_path: Path) -> None:
    with pytest.raises(SchemaVersionError, match="setup_db_schema"):
        ensure_db()


def test_populated_unversioned_database_is_rejected_with_baseline_command(db_path: Path) -> None:
    build_db_at_head(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("DROP TABLE alembic_version")
    conn.commit()
    conn.close()

    with pytest.raises(SchemaVersionError, match="baseline"):
        ensure_db()


def test_behind_database_is_rejected(db_path: Path) -> None:
    build_db_at_head(db_path)
    _set_version(db_path, "0000")
    with pytest.raises(SchemaVersionError, match="does not match the expected head"):
        ensure_db()


def test_ahead_database_is_rejected(db_path: Path) -> None:
    build_db_at_head(db_path)
    _set_version(db_path, "9999")
    with pytest.raises(SchemaVersionError, match="does not match the expected head"):
        ensure_db()


def test_branched_database_is_rejected(db_path: Path) -> None:
    build_db_at_head(db_path)
    _set_version(db_path, "0001", "0002")
    with pytest.raises(SchemaVersionError, match="branched"):
        ensure_db()


def test_rejected_connection_leaves_database_untouched(db_path: Path) -> None:
    sqlite3.connect(db_path).close()  # empty file, no schema
    with pytest.raises(SchemaVersionError):
        ensure_db()

    conn = sqlite3.connect(db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()[0] == 0
    finally:
        conn.close()


def test_db_session_yields_verified_connection(db_path: Path) -> None:
    build_db_at_head(db_path)
    with db_session() as conn:
        assert conn.execute("SELECT 1").fetchone()[0] == 1


def test_db_session_propagates_schema_error(db_path: Path) -> None:
    with pytest.raises(SchemaVersionError):
        with db_session():
            pass
