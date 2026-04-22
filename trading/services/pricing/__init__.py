"""Pricing service package.

This package is the stable public pricing surface.
"""

from trading.services.pricing.market_data import benchmark_stats, fetch_latest_prices

__all__ = [
    "benchmark_stats",
    "fetch_latest_prices",
]
