from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import pytest

import common.market_data as market_data


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


def test_yfinance_close_history_uses_file_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRADING_MARKET_DATA_CACHE_DIR", str(tmp_path))
    provider = market_data.YFinanceProvider()
    index = pd.date_range("2026-01-01", periods=3)
    hist = pd.DataFrame(
        {
            ("Close", "AAPL"): [100.0, 101.0, 102.0],
            ("Close", "MSFT"): [200.0, 201.0, 202.0],
        },
        index=index,
    )

    calls: list[object] = []

    def _fake_download(**kwargs):
        calls.append(kwargs)
        return hist

    monkeypatch.setattr("common.market_data.yf.download", _fake_download)

    first = provider.fetch_close_history(
        ["aapl", "msft"],
        pd.Timestamp("2026-01-01").date(),
        pd.Timestamp("2026-01-03").date(),
    )
    second = provider.fetch_close_history(
        ["AAPL", "MSFT"],
        pd.Timestamp("2026-01-01").date(),
        pd.Timestamp("2026-01-03").date(),
    )

    assert calls and len(calls) == 1
    pd.testing.assert_frame_equal(first, second)


def test_yfinance_close_series_uses_file_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRADING_MARKET_DATA_CACHE_DIR", str(tmp_path))
    provider = market_data.YFinanceProvider()
    index = pd.date_range("2026-01-01", periods=3)
    history = pd.DataFrame({"Close": [100.0, 101.0, 102.0]}, index=index)

    calls: list[str] = []

    class _FakeTicker:
        def __init__(self, ticker: str) -> None:
            self.ticker = ticker

        def history(self, *, period: str, auto_adjust: bool) -> pd.DataFrame:
            calls.append(f"{self.ticker}:{period}:{auto_adjust}")
            return history

    monkeypatch.setattr("common.market_data.yf.Ticker", _FakeTicker)

    first = provider.fetch_close_series("spy", "5d")
    second = provider.fetch_close_series("SPY", "5d")

    assert len(calls) == 1
    assert first is not None and second is not None
    pd.testing.assert_series_equal(first, second)


def test_stale_market_data_cache_refetches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRADING_MARKET_DATA_CACHE_DIR", str(tmp_path))
    provider = market_data.YFinanceProvider()
    index = pd.date_range("2026-01-01", periods=2)
    first_hist = pd.DataFrame({"Close": [100.0, 101.0]}, index=index)
    second_hist = pd.DataFrame({"Close": [102.0, 103.0]}, index=index)
    queued = [first_hist, second_hist]

    class _FakeTicker:
        def __init__(self, ticker: str) -> None:
            self.ticker = ticker

        def history(self, *, period: str, auto_adjust: bool) -> pd.DataFrame:
            return queued.pop(0)

    monkeypatch.setattr("common.market_data.yf.Ticker", _FakeTicker)

    first = provider.fetch_close_series("SPY", "5d")
    cache_files = list(tmp_path.glob("*.pkl"))
    assert len(cache_files) == 1

    stale_time = os.path.getmtime(cache_files[0]) - (market_data._MARKET_DATA_CACHE_TTL_SECONDS + 1)
    os.utime(cache_files[0], (stale_time, stale_time))

    second = provider.fetch_close_series("SPY", "5d")

    assert first is not None and second is not None
    assert float(first.iloc[-1]) == 101.0
    assert float(second.iloc[-1]) == 103.0
