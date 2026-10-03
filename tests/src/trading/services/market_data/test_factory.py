from __future__ import annotations

import pytest

from trading.services.market_data.factory import build_feature_provider
from trading.services.market_data.features import ProxyFeatureDataProvider
from trading.services.market_data.protocols import MarketDataProvider, require_feature_provider, require_provider


class _StubProvider(MarketDataProvider):
    def fetch_ohlcv(self, ticker, period, interval):  # pragma: no cover - not exercised
        raise NotImplementedError

    def fetch_close_history(self, tickers, start_date, end_date):  # pragma: no cover - not exercised
        raise NotImplementedError

    def fetch_close_series(self, ticker, period):  # pragma: no cover - not exercised
        raise NotImplementedError

    def fetch_bar_history(self, tickers, start_date, end_date):  # pragma: no cover - not exercised
        raise NotImplementedError


def test_build_feature_provider_injects_market_data_provider() -> None:
    provider = _StubProvider()

    feature_provider = build_feature_provider(market_data_provider=provider)

    assert isinstance(feature_provider, ProxyFeatureDataProvider)
    assert feature_provider._market_data_provider is provider


def test_require_provider_returns_injected_and_raises_on_none() -> None:
    provider: MarketDataProvider = _StubProvider()
    assert require_provider(provider) is provider

    with pytest.raises(ValueError, match="MarketDataProvider must be injected"):
        require_provider(None)


def test_require_feature_provider_returns_injected_and_raises_on_none() -> None:
    feature_provider = ProxyFeatureDataProvider(category_file="missing.txt")
    assert require_feature_provider(feature_provider) is feature_provider

    with pytest.raises(ValueError, match="FeatureDataProvider must be injected"):
        require_feature_provider(None)
