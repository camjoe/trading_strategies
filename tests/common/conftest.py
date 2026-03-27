from __future__ import annotations

from collections.abc import Iterator

import pytest

import common.market_data as market_data


@pytest.fixture(autouse=True)
def reset_provider_state(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.delenv("TRADING_MARKET_DATA_PROVIDER", raising=False)
    monkeypatch.delenv("TRADING_MARKET_DATA_CONFIG", raising=False)
    market_data.reload_provider_from_config()
    try:
        yield
    finally:
        monkeypatch.delenv("TRADING_MARKET_DATA_PROVIDER", raising=False)
        monkeypatch.delenv("TRADING_MARKET_DATA_CONFIG", raising=False)
        market_data.reload_provider_from_config()
