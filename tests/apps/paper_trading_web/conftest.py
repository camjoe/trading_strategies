from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from infrastructure.database.backend import SQLiteBackend, get_backend, set_backend
from tests.support.db_schema import build_db_at_head


@pytest.fixture
def api_client(tmp_path: Path) -> Iterator[TestClient]:
    original = get_backend()
    set_backend(SQLiteBackend(build_db_at_head(tmp_path / "paper_trading_web.db")))
    from paper_trading_web.backend.main import app

    try:
        with TestClient(app) as client:
            yield client
    finally:
        set_backend(original)
