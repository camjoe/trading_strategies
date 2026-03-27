from pathlib import Path

import pytest

from trading.database.db_backend import DatabaseBackend, SQLiteBackend, get_backend, set_backend


class StubBackend(DatabaseBackend):
    def __init__(self) -> None:
        self.open_called = False

    def open_connection(self) -> object:
        self.open_called = True
        return object()

    def run_script(self, conn: object, script: str) -> None:
        _ = (conn, script)

    def get_table_columns(self, conn: object, table: str) -> set[str]:
        _ = (conn, table)
        return {"id"}


class TestSQLiteBackend:
    def test_open_connection_creates_parent_and_sets_row_factory(self, tmp_path: Path) -> None:
        db_path = tmp_path / "nested" / "paper.db"
        backend = SQLiteBackend(db_path)

        conn = backend.open_connection()
        try:
            assert db_path.parent.exists()
            row = conn.execute("SELECT 1 AS n").fetchone()
            assert row is not None
            assert row["n"] == 1
        finally:
            conn.close()

    def test_run_script_and_get_table_columns(self, tmp_path: Path) -> None:
        backend = SQLiteBackend(tmp_path / "schema.db")
        conn = backend.open_connection()
        try:
            backend.run_script(
                conn,
                """
                CREATE TABLE sample (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL
                );
                """,
            )

            assert backend.get_table_columns(conn, "sample") == {"id", "name"}
        finally:
            conn.close()


class TestBackendRegistry:
    def test_set_backend_replaces_active_backend(self) -> None:
        original = get_backend()
        replacement = StubBackend()
        try:
            set_backend(replacement)
            assert get_backend() is replacement
        finally:
            set_backend(original)

    def test_stub_backend_open_connection_is_callable(self) -> None:
        backend = StubBackend()

        conn = backend.open_connection()

        assert backend.open_called is True
        assert conn is not None


@pytest.mark.parametrize(
    "table_name",
    ["accounts", "trades"],
)
def test_get_table_columns_returns_empty_set_for_missing_table(tmp_path: Path, table_name: str) -> None:
    backend = SQLiteBackend(tmp_path / "empty.db")
    conn = backend.open_connection()
    try:
        assert backend.get_table_columns(conn, table_name) == set()
    finally:
        conn.close()
