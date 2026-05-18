from __future__ import annotations

from pathlib import Path

import pytest

from trading.database.db_backend import SQLiteBackend, get_backend, set_backend


@pytest.fixture
def configured_backend(tmp_path: Path) -> SQLiteBackend:
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
