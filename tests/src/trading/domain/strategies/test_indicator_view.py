"""Precomputed indicators must equal what a signal would have derived itself."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from trading.domain.strategies.contracts import (
    INDICATOR_KIND_RETURN_VOL,
    INDICATOR_KIND_ROLLING_MAX,
    INDICATOR_KIND_ROLLING_MIN,
    INDICATOR_KIND_SMA,
    INDICATOR_KIND_STDDEV,
    INDICATOR_SOURCE_HIGH,
    INDICATOR_SOURCE_LOW,
    IndicatorSpec,
)
from trading.domain.strategies.indicator_view import (
    IndicatorView,
    build_indicator_arrays,
    count_priced_bars,
)
from trading.domain.strategies.registry import STRATEGY_REGISTRY


def _bars(n: int = 60) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=n, freq="B")
    close = pd.Series([100.0 + (i * 0.5) for i in range(n)], index=index)
    return pd.DataFrame(
        {
            "open": close.shift(1).fillna(close.iloc[0]),
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": pd.Series(1_000_000.0, index=index),
        }
    )


class TestWindowResolution:
    def test_knob_sets_the_window(self) -> None:
        spec = IndicatorSpec("ma", INDICATOR_KIND_SMA, window_param="fast_window", default_window=20)
        assert spec.window_for({"fast_window": 7}) == 7

    def test_default_applies_when_the_knob_is_absent(self) -> None:
        spec = IndicatorSpec("ma", INDICATOR_KIND_SMA, window_param="fast_window", default_window=20)
        assert spec.window_for({}) == 20

    def test_a_window_with_no_source_at_all_is_an_error(self) -> None:
        spec = IndicatorSpec("ma", INDICATOR_KIND_SMA)
        with pytest.raises(ValueError, match="neither a configured window nor a default"):
            spec.window_for({})


class TestComputation:
    def test_sma_matches_a_rolling_mean(self) -> None:
        bars = _bars()
        spec = IndicatorSpec("ma", INDICATOR_KIND_SMA, window_param="w", default_window=10)
        arrays = build_indicator_arrays(bars, (spec,), {"w": 10})
        expected = bars["close"].rolling(10).mean().to_numpy(dtype=float)
        np.testing.assert_allclose(arrays["ma"], expected, equal_nan=True)

    def test_stddev_is_the_population_deviation(self) -> None:
        """The band math it replaces used ddof=0; the sample deviation would widen bands."""
        bars = _bars()
        spec = IndicatorSpec("sd", INDICATOR_KIND_STDDEV, window_param="w", default_window=20)
        arrays = build_indicator_arrays(bars, (spec,), {"w": 20})
        expected = bars["close"].rolling(20).std(ddof=0).to_numpy(dtype=float)
        np.testing.assert_allclose(arrays["sd"], expected, equal_nan=True)

    def test_shift_excludes_the_current_bar(self) -> None:
        """A breakout compares against the prior window; including today's bar
        would compare a value against itself and never fire."""
        bars = _bars()
        spec = IndicatorSpec(
            "prior_high",
            INDICATOR_KIND_ROLLING_MAX,
            source=INDICATOR_SOURCE_HIGH,
            window_param="w",
            default_window=5,
            shift=1,
        )
        arrays = build_indicator_arrays(bars, (spec,), {"w": 5})
        last = len(bars) - 1
        assert arrays["prior_high"][last] == pytest.approx(bars["high"].iloc[last - 5 : last].max())

    def test_rolling_min_reads_its_declared_source_column(self) -> None:
        bars = _bars()
        spec = IndicatorSpec(
            "prior_low",
            INDICATOR_KIND_ROLLING_MIN,
            source=INDICATOR_SOURCE_LOW,
            window_param="w",
            default_window=5,
            shift=1,
        )
        arrays = build_indicator_arrays(bars, (spec,), {"w": 5})
        last = len(bars) - 1
        assert arrays["prior_low"][last] == pytest.approx(bars["low"].iloc[last - 5 : last].min())

    def test_return_vol_is_annualized_percent(self) -> None:
        bars = _bars()
        spec = IndicatorSpec("vol", INDICATOR_KIND_RETURN_VOL, window_param="w", default_window=20)
        arrays = build_indicator_arrays(bars, (spec,), {"w": 20})
        expected = bars["close"].pct_change().rolling(20).std(ddof=0) * (252**0.5) * 100.0
        np.testing.assert_allclose(arrays["vol"], expected.to_numpy(dtype=float), equal_nan=True)

    def test_a_missing_source_column_names_itself(self) -> None:
        """Reached when a strategy declares a high/low indicator but the caller
        only has closes — the message has to say which column is missing."""
        closes_only = pd.DataFrame({"close": [1.0, 2.0, 3.0]})
        spec = IndicatorSpec("h", INDICATOR_KIND_ROLLING_MAX, source=INDICATOR_SOURCE_HIGH, default_window=2)
        with pytest.raises(ValueError, match="needs bar column 'high'"):
            build_indicator_arrays(closes_only, (spec,), {})


class TestView:
    def test_offsets_read_backwards_from_the_current_bar(self) -> None:
        bars = _bars()
        spec = IndicatorSpec("ma", INDICATOR_KIND_SMA, window_param="w", default_window=5)
        arrays = build_indicator_arrays(bars, (spec,), {"w": 5})
        closes = bars["close"].to_numpy(dtype=float)
        view = IndicatorView(closes=closes, indicators=arrays, index=40)

        assert view.close() == pytest.approx(closes[40])
        assert view.close(-1) == pytest.approx(closes[39])
        assert view.value("ma") == pytest.approx(arrays["ma"][40])
        assert view.value("ma", -1) == pytest.approx(arrays["ma"][39])

    def test_reads_before_the_start_are_nan_not_errors(self) -> None:
        """Signals guard on finite values; raising here would turn a normal
        warm-up read into a crash."""
        bars = _bars()
        spec = IndicatorSpec("ma", INDICATOR_KIND_SMA, window_param="w", default_window=5)
        arrays = build_indicator_arrays(bars, (spec,), {"w": 5})
        view = IndicatorView(closes=bars["close"].to_numpy(dtype=float), indicators=arrays, index=0)

        assert np.isnan(view.value("ma", -1))
        assert np.isnan(view.close(-5))

    def test_an_undeclared_indicator_is_an_error(self) -> None:
        """A typo must fail loudly rather than read as a permanently missing value."""
        view = IndicatorView(closes=np.array([1.0]), indicators={}, index=0)
        with pytest.raises(KeyError, match="was not declared"):
            view.value("nope")

    def test_bars_counts_priced_bars_not_calendar_days(self) -> None:
        """History gates used to see a series with missing bars dropped out, so a
        late-listing ticker reached its minimum later than its calendar position."""
        closes = np.array([np.nan, np.nan, 10.0, 11.0, 12.0])
        view = IndicatorView(closes=closes, indicators={}, index=4, priced_bars=count_priced_bars(closes))
        assert view.bars() == 3


def test_every_registered_strategy_declares_the_indicators_it_reads() -> None:
    """A signal reading an undeclared indicator raises KeyError at evaluation
    time; running each strategy over real-shaped bars proves the wiring."""
    bars = _bars(n=90)
    closes = bars["close"].to_numpy(dtype=float)
    for strategy_id, spec in STRATEGY_REGISTRY.items():
        arrays = build_indicator_arrays(bars, spec.indicators, spec.default_params)
        view = IndicatorView(
            closes=closes, indicators=arrays, index=len(closes) - 1, priced_bars=count_priced_bars(closes)
        )
        assert spec.signal_fn(view, spec.default_params, None) in {"buy", "sell", "hold"}, strategy_id
