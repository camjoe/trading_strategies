from pathlib import Path

import pytest

from trading.database.code import db
from trading.database.code.db_backend import SQLiteBackend, get_backend, set_backend


@pytest.fixture
def conn(tmp_path: Path):
    original = get_backend()
    set_backend(SQLiteBackend(tmp_path / "paper_trading.db"))
    connection = db.ensure_db()
    try:
        yield connection
    finally:
        connection.close()
        set_backend(original)