"""Tests for the generated-fixture database build helpers.

Focused on the two properties that matter operationally: the delete guard can
only ever target an exact file under ``local/``, and a sandbox checkout really
does discard whatever the previous run wrote.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from scripts.fixture_db import (
    build_fixture_database,
    checkout_sandbox,
    exact_local_targets,
    golden_fingerprint,
)
from trading.services.fixtures import DEMO_PROFILE, SANDBOX_PROFILE

GOLDEN_NAME = "sandbox.golden.db"
WORKING_NAME = "sandbox.db"


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    (tmp_path / "local").mkdir()
    return tmp_path


def _account_names(database: Path) -> list[str]:
    conn = sqlite3.connect(database)
    try:
        return sorted(str(row[0]) for row in conn.execute("SELECT name FROM accounts"))
    finally:
        conn.close()


@pytest.mark.parametrize(
    "database_name",
    ["../escape.db", "nested/child.db", "local/../../outside.db"],
)
def test_exact_local_targets_rejects_paths_outside_local(tmp_path: Path, database_name: str) -> None:
    """The delete guard must refuse anything that is not a direct child of local/.

    These helpers drive ``unlink``, so a name that escapes the directory would
    delete an arbitrary file.
    """
    with pytest.raises(ValueError, match="exact filename directly under local/"):
        exact_local_targets(tmp_path, database_name)


def test_exact_local_targets_covers_the_sqlite_sidecars(tmp_path: Path) -> None:
    targets = exact_local_targets(tmp_path, "sandbox.db")
    assert [target.name for target in targets] == [
        "sandbox.db",
        "sandbox.db-shm",
        "sandbox.db-wal",
        "sandbox.db-journal",
    ]


def test_build_publishes_only_after_success(repo_root: Path) -> None:
    """A completed build leaves the final database and no preparing artifact."""
    database = build_fixture_database(
        repo_root,
        profile=DEMO_PROFILE,
        database_name="demo.db",
        preparing_name="demo.preparing.db",
    )
    assert database.exists()
    assert not (repo_root / "local" / "demo.preparing.db").exists()
    assert _account_names(database) == ["demo_momentum", "demo_trend"]


def test_checkout_rebuilds_once_then_reuses_the_golden(repo_root: Path) -> None:
    _, first_rebuilt = checkout_sandbox(
        repo_root,
        profile=DEMO_PROFILE,
        golden_name=GOLDEN_NAME,
        working_name=WORKING_NAME,
    )
    _, second_rebuilt = checkout_sandbox(
        repo_root,
        profile=DEMO_PROFILE,
        golden_name=GOLDEN_NAME,
        working_name=WORKING_NAME,
    )
    assert first_rebuilt is True
    assert second_rebuilt is False


def test_checkout_rebuilds_when_the_fingerprint_goes_stale(repo_root: Path) -> None:
    checkout_sandbox(
        repo_root,
        profile=DEMO_PROFILE,
        golden_name=GOLDEN_NAME,
        working_name=WORKING_NAME,
    )
    stamp = (repo_root / "local" / GOLDEN_NAME).with_suffix(".fingerprint")
    stamp.write_text("stale-fingerprint", encoding="utf-8")

    _, rebuilt = checkout_sandbox(
        repo_root,
        profile=DEMO_PROFILE,
        golden_name=GOLDEN_NAME,
        working_name=WORKING_NAME,
    )
    assert rebuilt is True
    assert stamp.read_text(encoding="utf-8").strip() == golden_fingerprint(profile=DEMO_PROFILE)


def test_checkout_discards_writes_made_to_the_previous_working_copy(repo_root: Path) -> None:
    """The core sandbox promise: nothing written to it survives the next run."""
    working, _ = checkout_sandbox(
        repo_root,
        profile=DEMO_PROFILE,
        golden_name=GOLDEN_NAME,
        working_name=WORKING_NAME,
    )
    original = _account_names(working)

    conn = sqlite3.connect(working)
    conn.execute("DELETE FROM equity_snapshots")
    conn.execute("UPDATE accounts SET name = 'tampered' WHERE id = (SELECT MIN(id) FROM accounts)")
    conn.commit()
    conn.close()

    restored, rebuilt = checkout_sandbox(
        repo_root,
        profile=DEMO_PROFILE,
        golden_name=GOLDEN_NAME,
        working_name=WORKING_NAME,
    )
    assert rebuilt is False, "a tampered working copy must not trigger a golden rebuild"
    assert _account_names(restored) == original

    conn = sqlite3.connect(restored)
    try:
        assert conn.execute("SELECT COUNT(*) FROM equity_snapshots").fetchone()[0] > 0
    finally:
        conn.close()


def test_fingerprint_distinguishes_profiles() -> None:
    assert golden_fingerprint(profile=DEMO_PROFILE) != golden_fingerprint(profile=SANDBOX_PROFILE)
