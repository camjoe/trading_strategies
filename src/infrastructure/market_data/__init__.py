"""Concrete market-data adapters and provider factory.

Houses the concrete ``MarketDataProvider`` implementations (the yfinance-backed
adapter and the unavailable-provider placeholders) plus the factory that routes
``provider`` selection and constructs them. The yfinance dependency is isolated
to this package.

The ``MarketDataProvider`` port and the transport cache live in
``trading.services.market_data`` (the adapter implements the port and reuses the
cache). ``src/trading/`` must never import from this package; the interface layer
and the backtest composition seam wire it in (mirroring ``infrastructure.brokers``).
"""

from __future__ import annotations

from .factory import build_provider
from .factory import resolve_provider_name
from .factory import supported_provider_names
from .demo_provider import DemoMarketDataProvider
from .unavailable_provider import UnavailableProvider
from .yfinance_provider import YFinanceProvider
from .yfinance_provider import yf

__all__ = [
    "UnavailableProvider",
    "DemoMarketDataProvider",
    "YFinanceProvider",
    "build_provider",
    "resolve_provider_name",
    "supported_provider_names",
    "yf",
]
