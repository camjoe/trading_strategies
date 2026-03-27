from pathlib import Path
import sqlite3
from collections.abc import Iterator

import pytest

from trading.database import db
from trading.database.db_backend import SQLiteBackend, get_backend, set_backend


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    original = get_backend()
    set_backend(SQLiteBackend(tmp_path / "paper_trading.db"))
    connection = db.ensure_db()
    try:
        yield connection
    finally:
        connection.close()
        set_backend(original)