from __future__ import annotations

import json
from pathlib import Path

import pytest

import common.market_data as market_data


@pytest.fixture(autouse=True)
def _reset_provider_state(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("TRADING_MARKET_DATA_PROVIDER", raising=False)
    monkeypatch.delenv("TRADING_MARKET_DATA_CONFIG", raising=False)
    market_data.reload_provider_from_config()
    yield
    monkeypatch.delenv("TRADING_MARKET_DATA_PROVIDER", raising=False)
    monkeypatch.delenv("TRADING_MARKET_DATA_CONFIG", raising=False)
    market_data.reload_provider_from_config()


def test_default_provider_is_yfinance() -> None:
    assert market_data.get_provider_name() == "yfinance"


def test_provider_can_be_selected_from_config_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = tmp_path / "market_data_config.json"
    config_path.write_text(json.dumps({"provider": "yfinance"}) + "\n", encoding="utf-8")
    monkeypatch.setenv("TRADING_MARKET_DATA_CONFIG", str(config_path))

    active = market_data.reload_provider_from_config()

    assert active == "yfinance"
    assert market_data.get_provider_name() == "yfinance"


def test_unknown_provider_name_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRADING_MARKET_DATA_PROVIDER", "not-a-real-provider")

    with pytest.raises(ValueError, match="Unsupported market data provider"):
        market_data.reload_provider_from_config()


def test_planned_provider_placeholder_is_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRADING_MARKET_DATA_PROVIDER", "ccxt")
    market_data.reload_provider_from_config()

    assert market_data.get_provider_name() == "ccxt"
    provider = market_data.get_provider()

    with pytest.raises(NotImplementedError, match="not implemented yet"):
        provider.fetch_close_series("SPY", "1mo")
