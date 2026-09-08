"""Concrete market-data provider factory.

Every call returns a fresh instance; nothing here is cached or global, so a
composition root builds one provider at entry and injects it down the chain.

``src/trading/`` must never import this module (enforced by
``scripts/checks/repo/layer_check.py``); the interface layer and the backtest
composition seam wire it in.
"""

from __future__ import annotations

import os
from collections.abc import Callable

from trading.services.market_data.protocols import MarketDataProvider

from .demo_provider import DemoMarketDataProvider
from .yfinance_provider import YFinanceProvider

_DEFAULT_PROVIDER_NAME = "yfinance"

_PROVIDER_FACTORIES: dict[str, Callable[[], MarketDataProvider]] = {
    "demo": DemoMarketDataProvider,
    "yfinance": YFinanceProvider,
}


def _provider_factory(name: str) -> Callable[[], MarketDataProvider]:
    factory = _PROVIDER_FACTORIES.get(name)
    if factory is None:
        supported = ", ".join(sorted(_PROVIDER_FACTORIES))
        raise ValueError(f"Unsupported market data provider '{name}'. Supported values: {supported}")
    return factory


def resolve_provider_name() -> str:
    """Resolve the configured provider name from the environment, then the default."""
    env_name = str(os.getenv("TRADING_MARKET_DATA_PROVIDER", "")).strip().lower()
    return env_name or _DEFAULT_PROVIDER_NAME


def build_provider(name: str | None = None) -> MarketDataProvider:
    """Build a fresh ``MarketDataProvider``, resolving *name* from the environment when omitted."""
    resolved = name.strip().lower() if name else resolve_provider_name()
    return _provider_factory(resolved)()
