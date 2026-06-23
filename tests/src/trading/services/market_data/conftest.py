from __future__ import annotations

from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True)
def reset_provider_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Keep provider resolution deterministic by clearing config env vars.

    Provider selection is now stateless (``build_provider``), so there is no
    global to reset — only the environment that feeds ``resolve_provider_name``.
    """
    monkeypatch.delenv("TRADING_MARKET_DATA_PROVIDER", raising=False)
    monkeypatch.delenv("TRADING_MARKET_DATA_CONFIG", raising=False)
    yield
