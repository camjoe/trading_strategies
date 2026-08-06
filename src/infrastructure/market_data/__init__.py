"""Concrete market-data adapters and the provider factory."""

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
