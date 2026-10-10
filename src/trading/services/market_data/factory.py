"""Builder for the (trading-side) feature provider.

The concrete market-data provider factory lives in
``infrastructure.market_data.factory`` (it constructs the yfinance-backed
adapter). The feature provider stays here because ``ProxyFeatureDataProvider``
is a trading-domain computation over an injected market-data provider — it has
no external-library dependency.
"""

from __future__ import annotations

from .features import ProxyFeatureDataProvider
from .protocols import FeatureDataProvider, MarketDataProvider


def build_feature_provider(
    *,
    market_data_provider: MarketDataProvider | None = None,
) -> FeatureDataProvider:
    """Build a fresh ``FeatureDataProvider`` backed by *market_data_provider*."""
    return ProxyFeatureDataProvider(market_data_provider=market_data_provider)
