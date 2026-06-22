from __future__ import annotations

import os
import sqlite3
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

from src.infrastructure.database.db_backend import SQLiteBackend, get_backend, set_backend
from src.infrastructure.database.db_init import ensure_db
from tests.support.seed.db import seed_session_db


@pytest.fixture(scope="session", autouse=True)
def _guard_sqlite_uri_readonly() -> None:
    """Abort the session if SQLite URI read-only mode is not functional.

    ``seeded_conn`` opens the seeded database with ``?mode=ro`` for OS-level
    read-only enforcement.  This guard verifies that mechanism actually blocks
    writes on the current SQLite build *before* any tests run.

    Unlike ``PRAGMA query_only``, the URI ``?mode=ro`` flag is enforced at the
    OS/VFS level: it prevents DML, DDL, COMMIT of pending writes, and WAL
    checkpoints, and causes ``sqlite3_db_readonly()`` to return 1.  The PRAGMA
    alone does not provide those guarantees (see SQLite docs).

    Exit code 3 causes GitHub Actions (and other CI) to mark the run failed.
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        setup = sqlite3.connect(db_path)
        setup.execute("CREATE TABLE _guard (x INTEGER)")
        setup.commit()
        setup.close()

        ro = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            ro.execute("INSERT INTO _guard VALUES (1)")
        except sqlite3.OperationalError:
            pass  # expected — URI read-only enforcement is working
        else:
            pytest.exit(
                "FATAL: SQLite URI read-only mode (file:...?mode=ro) did not block "
                "writes on this build.  seeded_conn integrity cannot be guaranteed.  "
                "Aborting test run.",
                returncode=3,
            )
        finally:
            ro.close()
    finally:
        os.unlink(db_path)


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
    """Session-scoped connection to a pre-seeded, OS-level read-only database.

    Use this fixture instead of ``conn`` for tests that only read or filter
    data — they get one shared DB per worker (pytest-xdist), seeded once,
    rather than a fresh DB per test.

    **How read-only is enforced:** after seeding, the writable connection is
    closed and the file is re-opened via SQLite's ``?mode=ro`` URI flag.  This
    is OS-level enforcement, stronger than ``PRAGMA query_only`` alone:

    - DML and DDL raise ``sqlite3.OperationalError`` immediately.
    - COMMIT of pending writes is rejected.
    - WAL checkpoints cannot proceed.
    - ``sqlite3_db_readonly()`` returns 1 (unlike the PRAGMA).

    The session-start guard ``_guard_sqlite_uri_readonly`` verifies this
    mechanism works before any tests run.

    Tests that write, delete, or depend on an empty table must use ``conn``.
    """
    tmp_path = tmp_path_factory.mktemp("seeded_db")
    db_path = tmp_path / "paper_trading_seeded.db"

    # Phase 1: seed via the standard backend so schema + seed data are written.
    original = get_backend()
    set_backend(SQLiteBackend(db_path))
    write_conn = ensure_db()
    seed_session_db(write_conn)
    write_conn.close()
    set_backend(original)

    # Phase 2: re-open at OS level as truly read-only.
    ro_conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    ro_conn.row_factory = sqlite3.Row
    try:
        yield ro_conn
    finally:
        ro_conn.close()
