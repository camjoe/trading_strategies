"""Concrete market-data adapters and provider factory.

Houses the concrete ``MarketDataProvider`` implementations (the yfinance-backed
adapter and the deterministic demo adapter) plus the factory that routes
``provider`` selection and constructs them. The yfinance dependency is isolated
to ``yfinance_provider``.

The ``MarketDataProvider`` port lives in ``trading.services.market_data`` (the
adapters implement it). ``src/trading/`` must never import from this package;
the interface layer and the backtest composition seam wire it in (mirroring
``infrastructure.brokers``).
"""

from __future__ import annotations

from .demo_provider import DemoMarketDataProvider
from .factory import build_provider, resolve_provider_name
from .yfinance_provider import YFinanceProvider

__all__ = [
    "DemoMarketDataProvider",
    "YFinanceProvider",
    "build_provider",
    "resolve_provider_name",
]
