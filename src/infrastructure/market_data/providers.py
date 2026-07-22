"""Compatibility imports for the split market-data provider modules."""

from __future__ import annotations

from .demo_provider import DemoMarketDataProvider
from .unavailable_provider import UnavailableProvider
from .yfinance_provider import YFinanceProvider
from .yfinance_provider import yf

__all__ = ["DemoMarketDataProvider", "UnavailableProvider", "YFinanceProvider", "yf"]
