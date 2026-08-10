import sqlite3
from pathlib import Path

import pytest

from trading.repositories import table_export


@pytest.fixture
def sqlite_db_file(tmp_path: Path) -> Path:
    db_path = tmp_path / "paper_trading.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE accounts (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL
            );
            CREATE TABLE notes (
                body TEXT NOT NULL
            );
            INSERT INTO accounts (id, name) VALUES (2, 'second');
            INSERT INTO accounts (id, name) VALUES (1, 'first');
            """
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


class TestNameValidation:
    def test_normalize_table_name_strips_invalid_characters(self) -> None:
        assert table_export.normalize_table_name(" Accounts;DROP ") == "accountsdrop"

    def test_normalize_table_name_rejects_empty_result(self) -> None:
        with pytest.raises(ValueError, match="Table name cannot be empty"):
            table_export.normalize_table_name("  ; ;  ")


class TestFetchTableCursor:
    def test_fetch_table_cursor_yields_header_and_rows_ordered_by_id(self, sqlite_db_file: Path) -> None:
        conn = sqlite3.connect(sqlite_db_file)
        try:
            normalized, header, cur = table_export.fetch_table_cursor(conn, "Accounts")
            rows = cur.fetchall()
        finally:
            conn.close()

        assert normalized == "accounts"
        assert header == ["id", "name"]
        assert rows == [(1, "first"), (2, "second")]

    def test_fetch_table_cursor_raises_for_unknown_table(self, sqlite_db_file: Path) -> None:
        conn = sqlite3.connect(sqlite_db_file)
        try:
            with pytest.raises(ValueError, match="Table not found: missing"):
                table_export.fetch_table_cursor(conn, "missing")
        finally:
            conn.close()


def test_ordered_select_sql_skips_ordering_when_table_has_no_id(sqlite_db_file: Path) -> None:
    conn = sqlite3.connect(sqlite_db_file)
    try:
        assert table_export._ordered_select_sql(conn, "notes") == "SELECT * FROM notes"
    finally:
        conn.close()
