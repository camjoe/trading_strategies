from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from trading.database.db_backend import SQLiteBackend, get_backend, set_backend
from trading.database.db_init import ensure_db
from tests.trading.services.admin.seed import seed_admin_db


@pytest.fixture
def configured_backend(tmp_path: Path) -> Iterator[SQLiteBackend]:
    """Isolated SQLite backend for admin tests.

    Admin service functions call ``ensure_db()`` internally, which requires
    a backend to be configured.  This fixture sets up a fresh per-test backend
    and restores the original on teardown.
    """
    original = get_backend()
    backend = SQLiteBackend(tmp_path / "paper_trading.db")
    set_backend(backend)
    try:
        yield backend
    finally:
        set_backend(original)


@pytest.fixture
def seeded_conn(configured_backend: SQLiteBackend) -> Iterator[sqlite3.Connection]:
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
