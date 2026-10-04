from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolate_market_data_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Pin provider resolution and the cache directory away from developer state.

    Without the cache-dir pin a test that fetches writes into the real
    ``local/cache/market_data``, where it can then satisfy a later run's read.
    """
    monkeypatch.delenv("TRADING_MARKET_DATA_PROVIDER", raising=False)
    monkeypatch.delenv("TRADING_MARKET_DATA_CACHE_DISABLED", raising=False)
    monkeypatch.setenv("TRADING_MARKET_DATA_CACHE_DIR", str(tmp_path / "market_data_cache"))
    yield
