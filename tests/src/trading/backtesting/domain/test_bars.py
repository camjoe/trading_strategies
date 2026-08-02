"""Aligning per-ticker bars onto one calendar must not invent or lose data."""

from __future__ import annotations

import pandas as pd
import pytest

from trading.backtesting.domain.bars import build_bar_panel
from trading.domain.strategies.contracts import INDICATOR_KIND_SMA, IndicatorSpec
from trading.domain.strategies.indicator_view import build_signal_inputs
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


class TestIndicatorsAreUniverseIndependent:
    """A ticker's indicators must not depend on which other tickers share the run.

    The panel's calendar is the union of every ticker's trading days, so a name
    that trades on days another does not adds carried-forward rows to that other
    ticker's frame. Computing a rolling window over those rows makes the result a
    property of the universe rather than of the instrument — and the live path,
    which only ever sees one ticker's own bars, would disagree with it.
    """

    # BBB trades weekly. Its own bars are identical in every case below.
    THIN = ["2024-01-01", "2024-01-08", "2024-01-15", "2024-01-22"]
    THIN_CLOSES = [20.0, 26.0, 30.0, 24.0]
    WINDOW = 4

    def _bbb_inputs(self, frames: dict[str, pd.DataFrame], tickers: list[str]):
        panel = build_bar_panel(frames, tickers)
        spec = (IndicatorSpec("ma", INDICATOR_KIND_SMA, default_window=self.WINDOW),)
        return build_signal_inputs(panel.source("BBB"), spec, {}, calendar=pd.DatetimeIndex(panel.dates))

    def test_adding_an_unrelated_ticker_does_not_move_the_indicator(self) -> None:
        bbb = _frame(self.THIN, self.THIN_CLOSES)
        aaa = _frame(self.THIN, [10.0, 11.0, 12.0, 13.0])
        # CCC trades every business day, including the days BBB does not.
        dense_days = [day.strftime("%Y-%m-%d") for day in pd.bdate_range("2024-01-01", "2024-01-22")]
        ccc = _frame(dense_days, [5.0] * len(dense_days))

        _, narrow, _ = self._bbb_inputs({"AAA": aaa, "BBB": bbb}, ["AAA", "BBB"])
        _, wide, _ = self._bbb_inputs({"AAA": aaa, "BBB": bbb, "CCC": ccc}, ["AAA", "BBB", "CCC"])

        # Mean of BBB's own last four closes. Before this was fixed the wide
        # universe gave 28.50, because CCC's extra days entered BBB's window.
        assert narrow["ma"][-1] == pytest.approx(25.0)
        assert wide["ma"][-1] == pytest.approx(25.0)

    def test_warm_up_gate_counts_real_bars_not_calendar_rows(self) -> None:
        bbb = _frame(self.THIN, self.THIN_CLOSES)
        dense_days = [day.strftime("%Y-%m-%d") for day in pd.bdate_range("2024-01-01", "2024-01-22")]
        ccc = _frame(dense_days, [5.0] * len(dense_days))

        _, _, priced = self._bbb_inputs({"BBB": bbb, "CCC": ccc}, ["BBB", "CCC"])

        # 16 calendar rows, but BBB only ever traded 4 times.
        assert len(priced) == len(dense_days)
        assert int(priced[-1]) == len(self.THIN)

    def test_values_carry_forward_between_the_ticker_s_own_bars(self) -> None:
        """A day BBB did not trade still needs a value: its last real one."""
        bbb = _frame(self.THIN, self.THIN_CLOSES)
        dense_days = [day.strftime("%Y-%m-%d") for day in pd.bdate_range("2024-01-01", "2024-01-22")]
        ccc = _frame(dense_days, [5.0] * len(dense_days))

        closes, indicators, _ = self._bbb_inputs({"BBB": bbb, "CCC": ccc}, ["BBB", "CCC"])
        calendar = pd.DatetimeIndex(dense_days)

        # The bar after BBB's last trade (2024-01-22) holds that trade's values.
        last_trade = calendar.get_loc(pd.Timestamp("2024-01-22"))
        assert closes[last_trade] == pytest.approx(self.THIN_CLOSES[-1])
        assert indicators["ma"][last_trade] == pytest.approx(25.0)
        # A gap day mid-series holds the value as of the preceding real bar.
        gap = calendar.get_loc(pd.Timestamp("2024-01-17"))
        assert closes[gap] == pytest.approx(30.0)
