"""Bar frames must be shaped and filled the same way whatever the provider."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

import infrastructure.market_data.yfinance_provider as provider_module
from infrastructure.market_data.demo_provider import DemoMarketDataProvider
from infrastructure.market_data.unavailable_provider import UnavailableProvider
from trading.models.market_data import BAR_CLOSE, BAR_COLUMNS, BAR_HIGH, BAR_LOW, BAR_OPEN, BAR_VOLUME


def _multi_ticker_download() -> pd.DataFrame:
    """A yfinance ``group_by="column"`` result: MultiIndex of (field, ticker)."""
    index = pd.date_range("2026-01-01", periods=4, freq="B")
    fields = {
        ("Open", "AAA"): [10.0, 11.0, 12.0, 13.0],
        ("High", "AAA"): [10.5, 11.5, 12.5, 13.5],
        ("Low", "AAA"): [9.5, 10.5, 11.5, 12.5],
        ("Close", "AAA"): [10.2, 11.2, 12.2, 13.2],
        ("Volume", "AAA"): [100.0, 200.0, 300.0, 400.0],
        ("Open", "BBB"): [20.0, None, 22.0, 23.0],
        ("High", "BBB"): [20.5, None, 22.5, 23.5],
        ("Low", "BBB"): [19.5, None, 21.5, 22.5],
        ("Close", "BBB"): [20.2, None, 22.2, 23.2],
        ("Volume", "BBB"): [500.0, None, 700.0, 800.0],
    }
    return pd.DataFrame(fields, index=index)


class TestSplitDownloadIntoBarFrames:
    def test_each_ticker_gets_its_own_frame_with_the_canonical_columns(self) -> None:
        frames = provider_module._split_download_into_bar_frames(_multi_ticker_download(), ["AAA", "BBB"])

        assert set(frames) == {"AAA", "BBB"}
        for frame in frames.values():
            assert tuple(frame.columns) == BAR_COLUMNS

    def test_prices_carry_forward_across_a_non_trading_day(self) -> None:
        """The last trade stays the best estimate of value when a ticker is quiet."""
        frames = provider_module._split_download_into_bar_frames(_multi_ticker_download(), ["AAA", "BBB"])

        gap_day = pd.Timestamp("2026-01-02")
        assert frames["BBB"].loc[gap_day, BAR_CLOSE] == 20.2
        assert frames["BBB"].loc[gap_day, BAR_HIGH] == 20.5

    def test_volume_is_zeroed_on_a_filled_day_rather_than_repeated(self) -> None:
        """A carried-forward volume would assert trading that never happened."""
        frames = provider_module._split_download_into_bar_frames(_multi_ticker_download(), ["AAA", "BBB"])

        assert frames["BBB"].loc[pd.Timestamp("2026-01-02"), BAR_VOLUME] == 0.0

    def test_a_ticker_with_no_bars_is_omitted(self) -> None:
        download = _multi_ticker_download()
        for field in ("Open", "High", "Low", "Close", "Volume"):
            download[(field, "BBB")] = None

        frames = provider_module._split_download_into_bar_frames(download, ["AAA", "BBB"])

        assert set(frames) == {"AAA"}

    def test_a_single_ticker_download_with_flat_columns_is_handled(self) -> None:
        index = pd.date_range("2026-01-01", periods=3, freq="B")
        flat = pd.DataFrame(
            {
                "Open": [10.0, 11.0, 12.0],
                "High": [10.5, 11.5, 12.5],
                "Low": [9.5, 10.5, 11.5],
                "Close": [10.2, 11.2, 12.2],
                "Volume": [100.0, 200.0, 300.0],
            },
            index=index,
        )

        frames = provider_module._split_download_into_bar_frames(flat, ["AAA"])

        assert tuple(frames["AAA"].columns) == BAR_COLUMNS
        assert frames["AAA"].loc[pd.Timestamp("2026-01-01"), BAR_CLOSE] == 10.2


class TestDemoProviderBars:
    def test_bars_obey_the_ohlc_invariants(self) -> None:
        """High bounds the bar above and low bounds it below, or true range is nonsense."""
        frames = DemoMarketDataProvider().fetch_bar_history(["AAA", "BBB"], date(2026, 1, 1), date(2026, 3, 1))

        for ticker, frame in frames.items():
            assert not frame.empty, ticker
            assert (frame[BAR_HIGH] >= frame[BAR_OPEN]).all(), ticker
            assert (frame[BAR_HIGH] >= frame[BAR_CLOSE]).all(), ticker
            assert (frame[BAR_LOW] <= frame[BAR_OPEN]).all(), ticker
            assert (frame[BAR_LOW] <= frame[BAR_CLOSE]).all(), ticker
            assert (frame[BAR_VOLUME] > 0).all(), ticker

    def test_bars_are_deterministic_across_calls(self) -> None:
        """The demo and fixture databases depend on this being reproducible."""
        first = DemoMarketDataProvider().fetch_bar_history(["AAA"], date(2026, 1, 1), date(2026, 2, 1))
        second = DemoMarketDataProvider().fetch_bar_history(["AAA"], date(2026, 1, 1), date(2026, 2, 1))

        pd.testing.assert_frame_equal(first["AAA"], second["AAA"])

    def test_close_matches_the_close_only_path(self) -> None:
        """Both reads describe the same synthetic market; they must not disagree."""
        provider = DemoMarketDataProvider()
        start, end = date(2026, 1, 1), date(2026, 2, 1)

        bars = provider.fetch_bar_history(["AAA"], start, end)
        closes = provider.fetch_close_history(["AAA"], start, end)

        pd.testing.assert_series_equal(
            bars["AAA"][BAR_CLOSE],
            closes["AAA"],
            check_names=False,
        )

    def test_empty_ticker_list_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="At least one ticker"):
            DemoMarketDataProvider().fetch_bar_history([], date(2026, 1, 1), date(2026, 2, 1))


def test_unavailable_provider_refuses_bar_history() -> None:
    with pytest.raises(NotImplementedError, match="not implemented yet"):
        UnavailableProvider("ccxt").fetch_bar_history(["AAA"], date(2026, 1, 1), date(2026, 2, 1))
