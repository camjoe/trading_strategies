from __future__ import annotations

import json

import pytest

from infrastructure.market_data import build_provider, supported_provider_names
from infrastructure.market_data.unavailable_provider import UnavailableProvider
from infrastructure.market_data.yfinance_provider import YFinanceProvider


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
