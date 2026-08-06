import sqlite3
from pathlib import Path

import pytest

from infrastructure.database.backend import SQLiteBackend, use_backend
from infrastructure.database.connection import SchemaVersionError
from tests.support.db_schema import build_db_at_head
from trading.interfaces.runtime.data_ops import csv_export


@pytest.fixture
def sqlite_db_file(tmp_path: Path) -> Path:
    # A migrated database, not a hand-rolled table: open_db_connection() gates
    # on the recorded schema revision before handing back the connection.
    return build_db_at_head(tmp_path / "paper_trading.db")


class TestOpenDbConnection:
    def test_open_db_connection_with_explicit_path(self, sqlite_db_file: Path) -> None:
        conn, resolved_path = csv_export.open_db_connection(sqlite_db_file)
        try:
            assert resolved_path == sqlite_db_file.resolve()
            assert conn.execute("SELECT 1 FROM accounts").fetchall() == []
        finally:
            conn.close()

    def test_open_db_connection_uses_active_backend_when_path_omitted(
        self, sqlite_db_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TRADING_DB_PATH", str(tmp_path / "missing.db"))
        with use_backend(SQLiteBackend(sqlite_db_file)):
            conn, resolved_path = csv_export.open_db_connection()

        try:
            assert resolved_path == sqlite_db_file.resolve()
        finally:
            conn.close()

    def test_open_db_connection_raises_when_db_file_missing(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="Database file not found"):
            csv_export.open_db_connection(tmp_path / "missing.db")

    def test_open_db_connection_rejects_database_off_the_expected_revision(self, tmp_path: Path) -> None:
        db_path = tmp_path / "unversioned.db"
        conn = sqlite3.connect(db_path)
        try:
            conn.execute("CREATE TABLE accounts (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
            conn.commit()
        finally:
            conn.close()

        with pytest.raises(SchemaVersionError, match="expected"):
            csv_export.open_db_connection(db_path)

    def test_open_db_connection_falls_back_to_get_db_path_for_non_sqlite_backend(
        self,
        sqlite_db_file: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        class _Backend:
            def open_connection(self):
                return sqlite3.connect(sqlite_db_file)

        monkeypatch.setattr(csv_export, "get_backend", lambda: _Backend())
        monkeypatch.setattr(csv_export, "get_db_path", lambda: sqlite_db_file)

        conn, resolved_path = csv_export.open_db_connection()
        try:
            assert resolved_path == sqlite_db_file.resolve()
        finally:
            conn.close()
