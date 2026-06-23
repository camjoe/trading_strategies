from __future__ import annotations

import json

import pytest

from trading.services.market_data import (
    MarketDataProvider,
    build_feature_provider,
    build_provider,
    require_feature_provider,
    require_provider,
    supported_provider_names,
)
from trading.services.market_data.features import ProxyFeatureDataProvider
from trading.services.market_data.providers import UnavailableProvider, YFinanceProvider


def test_supported_provider_names_include_default_and_placeholders() -> None:
    names = supported_provider_names()

    assert "yfinance" in names
    assert "alpha_vantage" in names
    assert tuple(sorted(names)) == names


def test_build_provider_defaults_to_yfinance() -> None:
    assert isinstance(build_provider(), YFinanceProvider)


def test_build_provider_by_name_returns_placeholder() -> None:
    assert isinstance(build_provider("stooq"), UnavailableProvider)


def test_build_provider_rejects_unknown_name() -> None:
    with pytest.raises(ValueError, match="Unsupported market data provider"):
        build_provider("unknown-feed")


def test_build_provider_reads_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRADING_MARKET_DATA_PROVIDER", "stooq")

    assert isinstance(build_provider(), UnavailableProvider)


def test_build_provider_reads_file_config(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    config_path = tmp_path / "market_data_config.json"
    config_path.write_text(json.dumps({"provider": "stooq"}), encoding="utf-8")
    monkeypatch.delenv("TRADING_MARKET_DATA_PROVIDER", raising=False)
    monkeypatch.setenv("TRADING_MARKET_DATA_CONFIG", str(config_path))

    assert isinstance(build_provider(), UnavailableProvider)


def test_build_feature_provider_injects_market_data_provider() -> None:
    provider = build_provider("stooq")

    feature_provider = build_feature_provider(market_data_provider=provider)

    assert isinstance(feature_provider, ProxyFeatureDataProvider)
    assert feature_provider._market_data_provider is provider


def test_require_provider_returns_injected_and_raises_on_none() -> None:
    provider: MarketDataProvider = YFinanceProvider()
    assert require_provider(provider) is provider

    with pytest.raises(ValueError, match="MarketDataProvider must be injected"):
        require_provider(None)


def test_require_feature_provider_returns_injected_and_raises_on_none() -> None:
    feature_provider = ProxyFeatureDataProvider(category_file="missing.txt")
    assert require_feature_provider(feature_provider) is feature_provider

    with pytest.raises(ValueError, match="FeatureDataProvider must be injected"):
        require_feature_provider(None)
