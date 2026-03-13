from pathlib import Path

import pytest

from trading import db


@pytest.fixture
def conn(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    test_db_path = tmp_path / "paper_trading.db"
    monkeypatch.setattr(db, "DB_PATH", test_db_path)
    connection = db.ensure_db()
    try:
        yield connection
    finally:
        connection.close()
