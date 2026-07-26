import sqlite3
from pathlib import Path

import pytest

from trading.services.table_export import stream_table_csv


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
            INSERT INTO accounts (id, name) VALUES (1, 'first');
            INSERT INTO accounts (id, name) VALUES (2, 'second');
            """
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


def test_stream_table_csv_yields_header_and_rows_ordered_by_id(sqlite_db_file: Path) -> None:
    conn = sqlite3.connect(sqlite_db_file)
    try:
        csv_text = "".join(stream_table_csv(conn, "accounts"))
    finally:
        conn.close()

    assert csv_text == "id,name\r\n1,first\r\n2,second\r\n"


def test_stream_table_csv_raises_for_unknown_table(sqlite_db_file: Path) -> None:
    conn = sqlite3.connect(sqlite_db_file)
    try:
        with pytest.raises(ValueError, match="Table not found: missing"):
            list(stream_table_csv(conn, "missing"))
    finally:
        conn.close()
