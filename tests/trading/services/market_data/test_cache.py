from __future__ import annotations

import io
import os
import pickle
import time
from pathlib import Path

import pandas as pd
import pytest

import trading.services.market_data.cache as cache_module
from trading.services.market_data.cache import (
    market_data_cache_dir,
    market_data_cache_disabled,
    market_data_cache_key,
    market_data_cache_path,
    read_market_data_cache,
    write_market_data_cache,
    _CACHE_MISS,
    _MARKET_DATA_CACHE_TTL_SECONDS,
)


def test_cache_disabled_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for value in ("1", "true", "yes", "on", "TRUE", "YES"):
        monkeypatch.setenv("TRADING_MARKET_DATA_CACHE_DISABLED", value)
        assert market_data_cache_disabled() is True
    monkeypatch.setenv("TRADING_MARKET_DATA_CACHE_DISABLED", "false")
    assert market_data_cache_disabled() is False


def test_cache_dir_uses_env_var(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRADING_MARKET_DATA_CACHE_DIR", str(tmp_path))
    assert market_data_cache_dir() == tmp_path.resolve()


def test_read_returns_cache_miss_when_disabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRADING_MARKET_DATA_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("TRADING_MARKET_DATA_CACHE_DISABLED", "1")
    key = market_data_cache_key("test", ticker="SPY")
    write_path = tmp_path / f"{key}.pkl"
    with write_path.open("wb") as f:
        pickle.dump(pd.Series([1.0, 2.0]), f)

    result = read_market_data_cache(key)
    assert result is _CACHE_MISS


def test_read_returns_cache_miss_when_pickle_is_corrupt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRADING_MARKET_DATA_CACHE_DIR", str(tmp_path))
    key = market_data_cache_key("test", ticker="CORRUPT")
    cache_path = tmp_path / f"{key}.pkl"
    cache_path.write_bytes(b"not-valid-pickle-data")

    result = read_market_data_cache(key)
    assert result is _CACHE_MISS


def test_read_returns_cache_miss_when_cached_type_is_wrong(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRADING_MARKET_DATA_CACHE_DIR", str(tmp_path))
    key = market_data_cache_key("test", ticker="WRONG_TYPE")
    cache_path = tmp_path / f"{key}.pkl"
    with cache_path.open("wb") as f:
        pickle.dump({"not": "a dataframe"}, f)

    result = read_market_data_cache(key)
    assert result is _CACHE_MISS


def test_write_then_read_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRADING_MARKET_DATA_CACHE_DIR", str(tmp_path))
    key = market_data_cache_key("close", ticker="AAPL", period="1y")
    series = pd.Series([100.0, 101.0, 102.0], name="Close")

    write_market_data_cache(key, series)
    result = read_market_data_cache(key)

    assert isinstance(result, pd.Series)
    pd.testing.assert_series_equal(result, series)


def test_write_is_noop_when_disabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRADING_MARKET_DATA_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("TRADING_MARKET_DATA_CACHE_DISABLED", "1")
    key = market_data_cache_key("close", ticker="AAPL")

    write_market_data_cache(key, pd.Series([1.0]))
    assert not (tmp_path / f"{key}.pkl").exists()
