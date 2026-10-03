"""The runtime account loader opens its own connection through the schema gate.

Job runners call this without an injected connection, so it is one of the few
places that reaches the backend from the service layer. It must still refuse a
database that is not at the expected revision, exactly as ``ensure_db()`` does.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from infrastructure.database.backend import SQLiteBackend, use_backend
from infrastructure.database.connection import SchemaVersionError, ensure_db
from trading.services.accounts.runtime_loader import load_account_names


def test_loader_returns_account_names(configured_backend: SQLiteBackend) -> None:
    conn = ensure_db()
    try:
        conn.execute(
            "INSERT INTO accounts (name, initial_cash, created_at, updated_at) VALUES (?, ?, ?, ?)",
            ("runtime-acct", 5000.0, "2026-03-27T08:09:10", "2026-03-27T08:09:10"),
        )
        conn.commit()
    finally:
        conn.close()

    assert load_account_names() == ["runtime-acct"]


def test_loader_rejects_a_database_off_the_expected_revision(tmp_path: Path) -> None:
    with use_backend(SQLiteBackend(tmp_path / "unversioned.db")):
        with pytest.raises(SchemaVersionError, match="manage_db_migrations status"):
            load_account_names()
