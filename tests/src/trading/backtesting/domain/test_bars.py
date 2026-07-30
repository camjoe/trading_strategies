"""Aligning per-ticker bars onto one calendar must not invent or lose data."""

from __future__ import annotations

import pandas as pd
import pytest

from trading.backtesting.domain.bars import build_bar_panel
from trading.models.market_data.constants import (
    BAR_CLOSE,
    BAR_COLUMNS,
    BAR_HIGH,
    BAR_LOW,
    BAR_OPEN,
    BAR_VOLUME,
)


def _frame(dates: list[str], closes: list[float]) -> pd.DataFrame:
    index = pd.to_datetime(dates)
    return pd.DataFrame(
        {
            BAR_OPEN: closes,
            BAR_HIGH: [value + 1.0 for value in closes],
            BAR_LOW: [value - 1.0 for value in closes],
            BAR_CLOSE: closes,
            BAR_VOLUME: [1000.0] * len(closes),
        },
        index=index,
    )[list(BAR_COLUMNS)]


class TestBuildBarPanel:
    def test_calendar_is_the_union_so_a_quiet_ticker_does_not_truncate_the_run(self) -> None:
        frames = {
            "AAA": _frame(["2026-01-05", "2026-01-06", "2026-01-07"], [10.0, 11.0, 12.0]),
            "BBB": _frame(["2026-01-05", "2026-01-07"], [20.0, 22.0]),
        }

        panel = build_bar_panel(frames, ["AAA", "BBB"])

        assert panel.dates == list(pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-07"]))

    def test_a_missing_day_carries_prices_forward_and_zeroes_volume(self) -> None:
        frames = {
            "AAA": _frame(["2026-01-05", "2026-01-06", "2026-01-07"], [10.0, 11.0, 12.0]),
            "BBB": _frame(["2026-01-05", "2026-01-07"], [20.0, 22.0]),
        }

        panel = build_bar_panel(frames, ["AAA", "BBB"])
        gap = pd.Timestamp("2026-01-06")

        assert panel.frame("BBB").loc[gap, BAR_CLOSE] == 20.0
        assert panel.frame("BBB").loc[gap, BAR_HIGH] == 21.0
        assert panel.frame("BBB").loc[gap, BAR_VOLUME] == 0.0

    def test_days_before_a_ticker_listed_stay_empty(self) -> None:
        """Back-filling would invent prices from before the ticker existed."""
        frames = {
            "OLD": _frame(["2026-01-05", "2026-01-06"], [10.0, 11.0]),
            "NEW": _frame(["2026-01-06"], [50.0]),
        }

        panel = build_bar_panel(frames, ["OLD", "NEW"])

        assert pd.isna(panel.frame("NEW").loc[pd.Timestamp("2026-01-05"), BAR_CLOSE])
        assert panel.frame("NEW").loc[pd.Timestamp("2026-01-06"), BAR_CLOSE] == 50.0

    def test_close_view_matches_the_per_ticker_frames(self) -> None:
        frames = {
            "AAA": _frame(["2026-01-05", "2026-01-06"], [10.0, 11.0]),
            "BBB": _frame(["2026-01-05", "2026-01-06"], [20.0, 21.0]),
        }

        panel = build_bar_panel(frames, ["AAA", "BBB"])

        assert list(panel.close.columns) == ["AAA", "BBB"]
        for ticker in ("AAA", "BBB"):
            pd.testing.assert_series_equal(
                panel.close[ticker],
                panel.frame(ticker)[BAR_CLOSE],
                check_names=False,
            )

    def test_low_stays_below_close_after_alignment(self) -> None:
        """Filling must not break the invariants indicators will rely on."""
        frames = {
            "AAA": _frame(["2026-01-05", "2026-01-06", "2026-01-07"], [10.0, 11.0, 12.0]),
            "BBB": _frame(["2026-01-05", "2026-01-07"], [20.0, 22.0]),
        }

        panel = build_bar_panel(frames, ["AAA", "BBB"])

        for ticker in ("AAA", "BBB"):
            frame = panel.frame(ticker).dropna()
            assert (frame[BAR_HIGH] >= frame[BAR_CLOSE]).all(), ticker
            assert (frame[BAR_LOW] <= frame[BAR_CLOSE]).all(), ticker

    def test_a_requested_ticker_with_no_frame_is_fatal(self) -> None:
        """Silently dropping it would backtest a smaller universe than asked for."""
        frames = {"AAA": _frame(["2026-01-05"], [10.0])}

        with pytest.raises(ValueError, match="Missing bar history for tickers: BBB"):
            build_bar_panel(frames, ["AAA", "BBB"])
