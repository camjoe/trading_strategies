"""The yfinance provider guards only real network fetches with its RateLimiter:
cache hits neither pace nor count, and an exhausted call budget raises."""

from __future__ import annotations

import pandas as pd
import pytest

import infrastructure.market_data.yfinance_provider as provider_module
from common.rate_limit import RateLimiter, RateLimitExceeded
from infrastructure.market_data.yfinance_provider import YFinanceProvider


def _vendor_download(rows: int = 2) -> pd.DataFrame:
    """A complete vendor OHLCV frame; these tests count limiter calls, not values."""
    return pd.DataFrame(
        {name: [float(row + 1) for row in range(rows)] for name in ("Open", "High", "Low", "Close", "Volume")}
    )


def test_network_fetch_acquires_one_slot(monkeypatch: pytest.MonkeyPatch) -> None:
    limiter = RateLimiter()
    monkeypatch.setattr(provider_module, "read_market_data_cache", lambda _key: provider_module._CACHE_MISS)
    monkeypatch.setattr(provider_module, "write_market_data_cache", lambda _key, _value: None)
    monkeypatch.setattr(provider_module.yf, "download", lambda *a, **k: _vendor_download())

    YFinanceProvider(rate_limiter=limiter).fetch_ohlcv("AAPL", "1mo", "1d")

    assert limiter.call_count == 1


def test_cache_hit_does_not_acquire(monkeypatch: pytest.MonkeyPatch) -> None:
    limiter = RateLimiter()
    cached = pd.DataFrame({"Close": [1.0]})
    monkeypatch.setattr(provider_module, "read_market_data_cache", lambda _key: cached)

    def _no_network(*_a, **_k):
        raise AssertionError("network must not be called on a cache hit")

    monkeypatch.setattr(provider_module.yf, "download", _no_network)

    result = YFinanceProvider(rate_limiter=limiter).fetch_ohlcv("AAPL", "1mo", "1d")

    assert result is cached
    assert limiter.call_count == 0


def test_exhausted_budget_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    limiter = RateLimiter(max_total_calls=1)
    monkeypatch.setattr(provider_module, "read_market_data_cache", lambda _key: provider_module._CACHE_MISS)
    monkeypatch.setattr(provider_module, "write_market_data_cache", lambda _key, _value: None)
    monkeypatch.setattr(provider_module.yf, "download", lambda *a, **k: _vendor_download(1))

    provider = YFinanceProvider(rate_limiter=limiter)
    provider.fetch_ohlcv("AAPL", "1mo", "1d")  # consumes the single allowed call

    with pytest.raises(RateLimitExceeded):
        provider.fetch_ohlcv("MSFT", "1mo", "1d")


def test_close_series_budget_error_is_not_swallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    # fetch_close_series wraps the network call in try/except that returns None on
    # failure; a RateLimitExceeded must escape that guard, not be reported as "no data".
    limiter = RateLimiter(max_total_calls=0)  # budget exhausted from the start
    monkeypatch.setattr(provider_module, "read_market_data_cache", lambda _key: provider_module._CACHE_MISS)

    with pytest.raises(RateLimitExceeded):
        YFinanceProvider(rate_limiter=limiter).fetch_close_series("SPY", "1mo")


def test_env_configures_the_default_limiter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRADING_YF_MAX_CALLS", "2")
    monkeypatch.setenv("TRADING_YF_MIN_INTERVAL_SECONDS", "0")
    limiter = provider_module.build_market_data_rate_limiter()

    limiter.acquire()
    limiter.acquire()
    with pytest.raises(RateLimitExceeded):
        limiter.acquire()
