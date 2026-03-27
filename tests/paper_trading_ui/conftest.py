from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from trading.database.code.db_backend import SQLiteBackend, get_backend, set_backend


@pytest.fixture
def api_client(tmp_path: Path) -> Iterator[TestClient]:
    original = get_backend()
    set_backend(SQLiteBackend(tmp_path / "paper_trading_ui.db"))
    from paper_trading_ui.backend.main import app

    try:
        with TestClient(app) as client:
            yield client
    finally:
        set_backend(original)
