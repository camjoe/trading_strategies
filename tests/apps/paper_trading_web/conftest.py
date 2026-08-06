from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from infrastructure.database.backend import SQLiteBackend, use_backend
from tests.support.db_schema import build_db_at_head


@pytest.fixture
def api_client(tmp_path: Path) -> Iterator[TestClient]:
    with use_backend(SQLiteBackend(build_db_at_head(tmp_path / "paper_trading_web.db"))):
        from paper_trading_web.backend.main import app

        with TestClient(app) as client:
            yield client
