import csv
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from trading.database import csv_export
from trading.database.db_backend import SQLiteBackend, get_backend, set_backend


class FixedDateTime:
    @classmethod
    def utcnow(cls) -> datetime:
        return datetime(2026, 3, 27, 12, 34, 56)


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
            CREATE TABLE trades (
                id INTEGER PRIMARY KEY,
                account_id INTEGER NOT NULL,
                ticker TEXT NOT NULL
            );
            INSERT INTO accounts (id, name) VALUES (2, 'second');
            INSERT INTO accounts (id, name) VALUES (1, 'first');
            INSERT INTO trades (id, account_id, ticker) VALUES (10, 1, 'SPY');
            """
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


def _read_csv_rows(path: Path) -> list[list[str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.reader(handle))


class TestNameAndPathValidation:
    def test_normalize_table_name_strips_invalid_characters(self) -> None:
        assert csv_export._normalize_table_name(" Accounts;DROP ") == "accountsdrop"

    def test_normalize_table_name_rejects_empty_result(self) -> None:
        with pytest.raises(ValueError, match="Table name cannot be empty"):
            csv_export._normalize_table_name("  ; ;  ")

    def test_zip_export_directory_rejects_missing_directory(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="Export directory not found"):
            csv_export.zip_export_directory(tmp_path / "missing")


class TestTableExport:
    def test_export_table_to_csv_writes_headers_and_orders_by_id(
        self, sqlite_db_file: Path, tmp_path: Path
    ) -> None:
        conn = sqlite3.connect(sqlite_db_file)
        try:
            output_path = tmp_path / "accounts.csv"
            result = csv_export.export_table_to_csv(conn, "accounts", output_path)
        finally:
            conn.close()

        rows = _read_csv_rows(output_path)
        assert rows[0] == ["id", "name"]
        assert rows[1] == ["1", "first"]
        assert rows[2] == ["2", "second"]
        assert result.row_count == 2
        assert result.table == "accounts"

    def test_export_table_to_csv_raises_for_unknown_table(self, sqlite_db_file: Path, tmp_path: Path) -> None:
        conn = sqlite3.connect(sqlite_db_file)
        try:
            with pytest.raises(ValueError, match="Table not found: missing"):
                csv_export.export_table_to_csv(conn, "missing", tmp_path / "missing.csv")
        finally:
            conn.close()


class TestBatchExport:
    def test_export_tables_to_csv_with_explicit_db_path(
        self, sqlite_db_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(csv_export, "datetime", FixedDateTime)

        result = csv_export.export_tables_to_csv(
            tables=["accounts", "trades"],
            output_base_dir=tmp_path,
            db_path=sqlite_db_file,
        )

        assert result.db_path == sqlite_db_file.resolve()
        assert result.output_dir.name == "db_csv_20260327_123456"
        assert result.started_at_utc == "2026-03-27T12:34:56Z"
        assert [item.table for item in result.tables] == ["accounts", "trades"]

        account_rows = _read_csv_rows(result.output_dir / "accounts.csv")
        trade_rows = _read_csv_rows(result.output_dir / "trades.csv")
        assert account_rows[1] == ["1", "first"]
        assert trade_rows[1] == ["10", "1", "SPY"]

    def test_export_tables_to_csv_uses_active_backend_when_db_path_omitted(
        self, sqlite_db_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(csv_export, "datetime", FixedDateTime)
        original = get_backend()
        set_backend(SQLiteBackend(sqlite_db_file))
        try:
            result = csv_export.export_tables_to_csv(
                tables=["accounts"],
                output_base_dir=tmp_path,
            )
        finally:
            set_backend(original)

        assert len(result.tables) == 1
        assert result.tables[0].row_count == 2

    def test_export_tables_to_csv_raises_when_db_file_missing(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="Database file not found"):
            csv_export.export_tables_to_csv(
                tables=["accounts"],
                output_base_dir=tmp_path,
                db_path=tmp_path / "missing.db",
            )

    def test_zip_export_directory_creates_archive(
        self, sqlite_db_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(csv_export, "datetime", FixedDateTime)
        batch = csv_export.export_tables_to_csv(
            tables=["accounts"],
            output_base_dir=tmp_path,
            db_path=sqlite_db_file,
        )

        archive = csv_export.zip_export_directory(batch.output_dir)

        assert archive.exists()
        assert archive.suffix == ".zip"
