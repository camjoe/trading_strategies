from pathlib import Path
import sqlite3
from collections.abc import Iterator

import pytest

from trading.database.db_backend import SQLiteBackend, get_backend, set_backend
from trading.database.db_init import ensure_db
from tests.support.seed_db import seed_session_db


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    original = get_backend()
    set_backend(SQLiteBackend(tmp_path / "paper_trading.db"))
    connection = ensure_db()
    try:
        yield connection
    finally:
        connection.close()
        set_backend(original)


@pytest.fixture(scope="session")
def seeded_conn(tmp_path_factory: pytest.TempPathFactory) -> Iterator[sqlite3.Connection]:
    """Session-scoped connection to a pre-seeded database.

    Use this fixture instead of ``conn`` for tests that only read or filter
    data — they get one shared DB per worker (pytest-xdist), seeded once,
    rather than a fresh DB per test.

    **Do not mutate the database from tests using this fixture.**  Any write
    will corrupt the shared state for all subsequent tests in the same worker.
    Tests that write, delete, or depend on an empty table must use ``conn``.
    """
    tmp_path = tmp_path_factory.mktemp("seeded_db")
    original = get_backend()
    set_backend(SQLiteBackend(tmp_path / "paper_trading_seeded.db"))
    connection = ensure_db()
    seed_session_db(connection)
    try:
        yield connection
    finally:
        connection.close()
        set_backend(original)
