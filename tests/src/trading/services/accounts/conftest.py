from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from infrastructure.database.backend import SQLiteBackend, get_backend, set_backend
from infrastructure.database.connection import ensure_db
from tests.src.trading.services.accounts.seed import seed_admin_db
from tests.support.db_schema import build_db_at_head
from trading.services.accounts import create_account


@pytest.fixture
def base_account(conn) -> str:
    """Plain account ready for configure/validation tests."""
    create_account(conn, "acct", "Trend", 3000.0, "SPY")
    return "acct"


@pytest.fixture
def configured_backend(tmp_path: Path) -> Iterator[SQLiteBackend]:
    """Isolated SQLite backend for deletion tests.

    Deletion service functions call ``ensure_db()`` internally, which requires
    a backend to be configured.  This fixture sets up a fresh per-test backend
    and restores the original on teardown.
    """
    original = get_backend()
    backend = SQLiteBackend(build_db_at_head(tmp_path / "paper_trading.db"))
    set_backend(backend)
    try:
        yield backend
    finally:
        set_backend(original)


@pytest.fixture
def deletion_empty_conn(configured_backend: SQLiteBackend) -> Iterator[sqlite3.Connection]:
    """Schema-initialised backend connection with no seeded rows.

    Use this when the test needs a configured backend but should start with an
    empty database (e.g. testing behaviour when no accounts exist).
    """
    conn = ensure_db()
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def deletion_seeded_conn(configured_backend: SQLiteBackend) -> Iterator[sqlite3.Connection]:
    """Fresh backend pre-populated with the canonical admin test dataset.

    Depends on ``configured_backend`` so the global backend is set before
    ``ensure_db()`` is called.  Tests that modify data (deletions, mutations)
    should use this fixture instead of calling ``seed_admin_db()`` directly.
    """
    conn = ensure_db()
    seed_admin_db(conn)
    try:
        yield conn
    finally:
        conn.close()
