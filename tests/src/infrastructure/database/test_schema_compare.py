"""Tests for the normalized schema comparator shared by baseline and verify."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from infrastructure.database import migration_runner
from infrastructure.database.backend import SQLiteBackend, get_backend, set_backend
from infrastructure.database.init import ensure_db
from infrastructure.database.schema_compare import compare_schemas


@pytest.fixture
def memory_pair() -> Any:
    expected = sqlite3.connect(":memory:")
    actual = sqlite3.connect(":memory:")
    try:
        yield expected, actual
    finally:
        expected.close()
        actual.close()


def test_alembic_and_probe_built_schemas_match(tmp_path: Path) -> None:
    migrated = sqlite3.connect(tmp_path / "via_alembic.db")
    migration_runner.upgrade("head", connection=migrated)

    original = get_backend()
    set_backend(SQLiteBackend(tmp_path / "via_init.db"))
    try:
        probe_built = ensure_db()
    finally:
        set_backend(original)

    try:
        comparison = compare_schemas(migrated, probe_built)
        assert comparison.matches, comparison.differences
    finally:
        migrated.close()
        probe_built.close()


def test_identical_databases_match(memory_pair: Any) -> None:
    expected, actual = memory_pair
    for conn in (expected, actual):
        conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT NOT NULL DEFAULT 'x')")
        conn.execute("CREATE INDEX idx_t_name ON t(name)")
    assert compare_schemas(expected, actual).matches


def test_column_order_is_ignored(memory_pair: Any) -> None:
    expected, actual = memory_pair
    expected.execute("CREATE TABLE t (a TEXT, b INTEGER)")
    actual.execute("CREATE TABLE t (b INTEGER, a TEXT)")
    assert compare_schemas(expected, actual).matches


def test_missing_and_unexpected_columns_are_reported(memory_pair: Any) -> None:
    expected, actual = memory_pair
    expected.execute("CREATE TABLE t (a TEXT, b INTEGER)")
    actual.execute("CREATE TABLE t (a TEXT, c REAL)")
    differences = compare_schemas(expected, actual).differences
    assert any("table t columns: missing" in d and "'b'" in d for d in differences)
    assert any("table t columns: unexpected" in d and "'c'" in d for d in differences)


def test_missing_table_is_reported(memory_pair: Any) -> None:
    expected, actual = memory_pair
    expected.execute("CREATE TABLE only_expected (id INTEGER)")
    differences = compare_schemas(expected, actual).differences
    assert differences == ["tables: missing 'only_expected'"]


def test_index_drift_is_reported(memory_pair: Any) -> None:
    expected, actual = memory_pair
    for conn in (expected, actual):
        conn.execute("CREATE TABLE t (a TEXT)")
    expected.execute("CREATE INDEX idx_t_a ON t(a)")
    differences = compare_schemas(expected, actual).differences
    assert differences == ["indexes: missing 'idx_t_a'"]


def test_index_definition_difference_is_reported(memory_pair: Any) -> None:
    expected, actual = memory_pair
    for conn in (expected, actual):
        conn.execute("CREATE TABLE t (a TEXT, b TEXT)")
    expected.execute("CREATE INDEX idx_t ON t(a)")
    actual.execute("CREATE INDEX idx_t ON t(b)")
    differences = compare_schemas(expected, actual).differences
    assert len(differences) == 1
    assert differences[0].startswith("index idx_t: definition differs")


def test_if_not_exists_and_whitespace_are_normalized(memory_pair: Any) -> None:
    expected, actual = memory_pair
    expected.execute("CREATE TABLE t (a TEXT)")
    expected.execute("CREATE INDEX IF NOT EXISTS idx_t_a\nON t(a)")
    actual.execute("CREATE TABLE t (a TEXT)")
    actual.execute("CREATE INDEX idx_t_a ON t(a)")
    assert compare_schemas(expected, actual).matches


def test_check_constraint_drift_is_reported(memory_pair: Any) -> None:
    expected, actual = memory_pair
    expected.execute("CREATE TABLE t (side TEXT CHECK (side IN ('buy', 'sell')))")
    actual.execute("CREATE TABLE t (side TEXT)")
    differences = compare_schemas(expected, actual).differences
    assert differences == ["table t checks: missing 'CHECK (side IN ('buy', 'sell'))'"]


def test_foreign_key_action_difference_is_reported(memory_pair: Any) -> None:
    expected, actual = memory_pair
    for conn in (expected, actual):
        conn.execute("CREATE TABLE parent (id INTEGER PRIMARY KEY)")
    expected.execute("CREATE TABLE child (pid INTEGER, FOREIGN KEY (pid) REFERENCES parent(id) ON DELETE CASCADE)")
    actual.execute("CREATE TABLE child (pid INTEGER, FOREIGN KEY (pid) REFERENCES parent(id))")
    differences = compare_schemas(expected, actual).differences
    assert any("table child foreign_keys" in d and "CASCADE" in d for d in differences)


def test_watchlist_default_value_is_compared_by_presence_only(memory_pair: Any) -> None:
    expected, actual = memory_pair
    expected.execute(
        "CREATE TABLE accounts (id INTEGER PRIMARY KEY, rotation_overlay_watchlist TEXT NOT NULL DEFAULT '[\"AAPL\"]')"
    )
    actual.execute(
        "CREATE TABLE accounts (id INTEGER PRIMARY KEY, "
        'rotation_overlay_watchlist TEXT NOT NULL DEFAULT \'["TSLA","XOM"]\')'
    )
    assert compare_schemas(expected, actual).matches


def test_watchlist_default_must_still_exist(memory_pair: Any) -> None:
    expected, actual = memory_pair
    expected.execute(
        "CREATE TABLE accounts (id INTEGER PRIMARY KEY, rotation_overlay_watchlist TEXT NOT NULL DEFAULT '[\"AAPL\"]')"
    )
    actual.execute("CREATE TABLE accounts (id INTEGER PRIMARY KEY, rotation_overlay_watchlist TEXT NOT NULL)")
    assert not compare_schemas(expected, actual).matches


def test_other_default_value_differences_are_reported(memory_pair: Any) -> None:
    expected, actual = memory_pair
    expected.execute("CREATE TABLE t (kind TEXT NOT NULL DEFAULT 'a')")
    actual.execute("CREATE TABLE t (kind TEXT NOT NULL DEFAULT 'b')")
    assert not compare_schemas(expected, actual).matches
