from __future__ import annotations

import pickle
from pathlib import Path

import pandas as pd
import pytest

from infrastructure.market_data.cache import (
    _CACHE_MISS,
    market_data_cache_dir,
    market_data_cache_disabled,
    market_data_cache_key,
    read_market_data_cache,
    write_market_data_cache,
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
        pickle.dump("not market data at all", f)

    result = read_market_data_cache(key)
    assert result is _CACHE_MISS


def test_a_dict_of_frames_survives_the_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A shape the type guard accepts must not read back as a miss."""
    monkeypatch.setenv("TRADING_MARKET_DATA_CACHE_DIR", str(tmp_path))
    key = market_data_cache_key("bar-history", tickers=["AAPL", "MSFT"])
    frames = {
        "AAPL": pd.DataFrame({"close": [100.0, 101.0]}),
        "MSFT": pd.DataFrame({"close": [200.0, 202.0]}),
    }

    write_market_data_cache(key, frames)
    result = read_market_data_cache(key)

    assert isinstance(result, dict)
    assert set(result) == {"AAPL", "MSFT"}
    for ticker, frame in frames.items():
        pd.testing.assert_frame_equal(result[ticker], frame)


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
