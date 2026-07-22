from __future__ import annotations

from datetime import date

import pandas as pd

from infrastructure.market_data import DemoMarketDataProvider, build_provider, supported_provider_names


def test_demo_provider_is_registered_and_deterministic() -> None:
    assert "demo" in supported_provider_names()
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

    assert frame.columns.tolist() == ["Open", "High", "Low", "Close", "Volume"]
    assert not frame.empty
