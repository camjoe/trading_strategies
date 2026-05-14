from __future__ import annotations

import json

import pytest

import trading.services.market_data.runtime as market_data_runtime
from trading.services.market_data.features import ProxyFeatureDataProvider
from trading.services.market_data.providers import UnavailableProvider, YFinanceProvider


@pytest.fixture
def restore_market_data_runtime():
    original_provider = market_data_runtime._provider
    original_provider_name = market_data_runtime._provider_name
    original_provider_source = market_data_runtime._provider_source
    original_provider_config_mtime = market_data_runtime._provider_config_mtime
    original_feature_provider = market_data_runtime._feature_provider
    try:
        yield
    finally:
        market_data_runtime._provider = original_provider
        market_data_runtime._provider_name = original_provider_name
        market_data_runtime._provider_source = original_provider_source
        market_data_runtime._provider_config_mtime = original_provider_config_mtime
        market_data_runtime._feature_provider = original_feature_provider


def test_supported_provider_names_include_default_and_placeholders() -> None:
    names = market_data_runtime.supported_provider_names()

    assert "yfinance" in names
    assert "alpha_vantage" in names
    assert tuple(sorted(names)) == names


def test_set_provider_by_name_switches_provider_implementation(restore_market_data_runtime) -> None:
    market_data_runtime.set_provider_by_name("stooq")

    provider = market_data_runtime.get_provider()

    assert isinstance(provider, UnavailableProvider)
    assert market_data_runtime.get_provider_name() == "stooq"


def test_set_provider_by_name_rejects_unknown_provider(restore_market_data_runtime) -> None:
    with pytest.raises(ValueError, match="Unsupported market data provider"):
        market_data_runtime.set_provider_by_name("unknown-feed")


def test_reload_provider_from_env_config(restore_market_data_runtime, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRADING_MARKET_DATA_PROVIDER", "yfinance")

    name = market_data_runtime.reload_provider_from_config()

    assert name == "yfinance"
    assert isinstance(market_data_runtime.get_provider(), YFinanceProvider)


def test_reload_provider_from_file_config(
    restore_market_data_runtime, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    config_path = tmp_path / "market_data_config.json"
    config_path.write_text(json.dumps({"provider": "stooq"}), encoding="utf-8")
    monkeypatch.delenv("TRADING_MARKET_DATA_PROVIDER", raising=False)
    monkeypatch.setenv("TRADING_MARKET_DATA_CONFIG", str(config_path))

    name = market_data_runtime.reload_provider_from_config()

    assert name == "stooq"
    assert isinstance(market_data_runtime.get_provider(), UnavailableProvider)


def test_set_feature_provider_updates_runtime_state(restore_market_data_runtime) -> None:
    provider = ProxyFeatureDataProvider(category_file="missing.txt")

    market_data_runtime.set_feature_provider(provider)

    assert market_data_runtime.get_feature_provider() is provider
