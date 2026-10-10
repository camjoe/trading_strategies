from __future__ import annotations

from datetime import date

import pandas as pd

from infrastructure.market_data import DemoMarketDataProvider, build_provider
from trading.models.market_data import BAR_CLOSE, BAR_COLUMNS, BAR_HIGH, BAR_LOW, BAR_OPEN


def test_demo_provider_is_registered_and_deterministic() -> None:
    provider = build_provider("demo")
    assert isinstance(provider, DemoMarketDataProvider)
    start = date(2026, 1, 1)
    end = date(2026, 1, 12)

    first = provider.fetch_close_history(["aapl", "XYZ"], start, end)
    second = provider.fetch_close_history(["AAPL", "xyz"], start, end)

    pd.testing.assert_frame_equal(first, second)
    assert list(first.columns) == ["AAPL", "XYZ"]
    assert first.index.min().date() >= start
    assert first.index.max().date() <= end


def test_demo_provider_returns_normal_ohlcv_shape() -> None:
    frame = DemoMarketDataProvider().fetch_ohlcv("ANY-TICKER", "1mo", "1d")

    assert tuple(frame.columns) == BAR_COLUMNS
    assert not frame.empty


def test_daily_ohlcv_agrees_with_the_bar_history_path() -> None:
    """Both reads describe the same synthetic market, so they must not disagree."""
    provider = DemoMarketDataProvider()
    ohlcv = provider.fetch_ohlcv("AAA", "1mo", "1d")
    bars = provider.fetch_bar_history(["AAA"], ohlcv.index.min().date(), ohlcv.index.max().date())["AAA"]

    pd.testing.assert_frame_equal(ohlcv.loc[bars.index], bars)


def test_ohlcv_obeys_the_ohlc_invariants_at_every_interval() -> None:
    provider = DemoMarketDataProvider()

    for interval in ("1d", "1wk", "1mo"):
        frame = provider.fetch_ohlcv("AAA", "1y", interval)
        assert not frame.empty, interval
        assert (frame[BAR_HIGH] >= frame[BAR_OPEN]).all(), interval
        assert (frame[BAR_HIGH] >= frame[BAR_CLOSE]).all(), interval
        assert (frame[BAR_LOW] <= frame[BAR_OPEN]).all(), interval
        assert (frame[BAR_LOW] <= frame[BAR_CLOSE]).all(), interval
