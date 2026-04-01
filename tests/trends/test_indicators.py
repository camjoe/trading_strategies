import math

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from trends.indicators import (
    add_trend_features,
    calculate_bollinger_bands,
    calculate_macd,
    calculate_rs_rsi,
)


# ---------------------------------------------------------------------------
# Existing tests (preserved)
# ---------------------------------------------------------------------------


def test_calculate_rs_rsi_shapes() -> None:
    close = pd.Series([100, 101, 102, 100, 103, 104, 103, 105, 106, 105, 107, 108, 109, 110, 111])

    rs, rsi = calculate_rs_rsi(close, window=5)

    assert len(rs) == len(close)
    assert len(rsi) == len(close)
    assert rsi.dropna().between(0, 100).all()


def test_calculate_macd_returns_three_series() -> None:
    close = pd.Series(np.linspace(100, 120, 40))

    macd, signal, hist = calculate_macd(close)

    assert len(macd) == len(close)
    assert len(signal) == len(close)
    assert len(hist) == len(close)
    assert (hist == (macd - signal)).all()


def test_add_trend_features_adds_expected_columns() -> None:
    df = pd.DataFrame(
        {
            "Close": np.linspace(100, 140, 220),
            "Volume": np.linspace(1_000_000, 2_000_000, 220),
        }
    )

    out = add_trend_features(df)

    expected = {"MA20", "MA50", "MA200", "RS", "RSI14", "MACD", "MACDSignal", "MACDHist", "DailyReturnPct"}
    assert expected.issubset(set(out.columns))
    assert out["MA20"].notna().sum() > 0
    assert out["MACD"].notna().sum() > 0
    assert out["DailyReturnPct"].notna().sum() > 0


# ---------------------------------------------------------------------------
# RSI edge cases
# ---------------------------------------------------------------------------


class TestCalculateRsRsiEdgeCases:
    def test_empty_series_returns_empty_series(self) -> None:
        rs, rsi = calculate_rs_rsi(pd.Series([], dtype=float))

        assert len(rs) == 0
        assert len(rsi) == 0

    def test_single_element_series_returns_all_nan(self) -> None:
        rs, rsi = calculate_rs_rsi(pd.Series([100.0]))

        assert len(rs) == 1
        assert rs.isna().all()
        assert rsi.isna().all()

    def test_all_nan_series_all_nan_output(self) -> None:
        rs, rsi = calculate_rs_rsi(pd.Series([float("nan")] * 20))

        assert rsi.isna().all()

    def test_constant_prices_produce_neutral_rsi(self) -> None:
        rs, rsi = calculate_rs_rsi(pd.Series([100.0] * 20), window=5)

        valid_rsi = rsi.dropna()
        assert not valid_rsi.empty
        assert np.allclose(valid_rsi.values, 50.0, atol=1e-9)

    def test_all_zeros_series_produces_neutral_rsi(self) -> None:
        rs, rsi = calculate_rs_rsi(pd.Series([0.0] * 20), window=5)

        valid_rsi = rsi.dropna()
        assert np.allclose(valid_rsi.values, 50.0, atol=1e-9)

    def test_pos_inf_values_do_not_raise(self) -> None:
        close = pd.Series([100.0] * 10 + [float("inf")] + [100.0] * 9)

        rs, rsi = calculate_rs_rsi(close, window=5)

        assert len(rsi) == 20

    def test_neg_inf_values_do_not_raise(self) -> None:
        close = pd.Series([100.0] * 10 + [float("-inf")] + [100.0] * 9)

        rs, rsi = calculate_rs_rsi(close, window=5)

        assert len(rsi) == 20

    def test_inf_values_yield_nan_not_inf_in_output(self) -> None:
        # inf in input is coerced to NaN; no inf should survive into RSI output.
        close = pd.Series([100.0] * 5 + [float("inf")] * 10 + [100.0] * 5)

        _rs, rsi = calculate_rs_rsi(close, window=5)

        assert not rsi.apply(lambda v: math.isinf(v) if pd.notna(v) else False).any()

    def test_rsi_always_in_0_to_100_for_random_walk(self) -> None:
        rng = np.random.default_rng(42)
        prices = pd.Series(100.0 + np.cumsum(rng.normal(0, 1, 100)))

        _, rsi = calculate_rs_rsi(prices, window=14)

        valid = rsi.dropna()
        assert (valid >= 0.0).all()
        assert (valid <= 100.0).all()

    def test_monotonically_rising_prices_rsi_at_100(self) -> None:
        close = pd.Series([float(i) for i in range(1, 30)])

        _, rsi = calculate_rs_rsi(close, window=14)

        assert rsi.dropna().iloc[-1] == pytest.approx(100.0, abs=1e-9)

    def test_monotonically_falling_prices_rsi_at_0(self) -> None:
        close = pd.Series([float(29 - i) for i in range(30)])

        _, rsi = calculate_rs_rsi(close, window=14)

        assert rsi.dropna().iloc[-1] == pytest.approx(0.0, abs=1e-9)

    def test_output_length_always_matches_input(self) -> None:
        for n in (1, 5, 14, 50):
            close = pd.Series([100.0] * n)
            rs, rsi = calculate_rs_rsi(close, window=5)
            assert len(rs) == n
            assert len(rsi) == n

    def test_very_large_prices_do_not_overflow(self) -> None:
        close = pd.Series([1e200 + float(i) for i in range(20)])

        _rs, rsi = calculate_rs_rsi(close, window=5)

        valid = rsi.dropna()
        assert (valid >= 0.0).all()
        assert (valid <= 100.0).all()

    def test_very_small_prices_do_not_underflow(self) -> None:
        close = pd.Series([1e-100 + float(i) * 1e-102 for i in range(20)])

        _rs, rsi = calculate_rs_rsi(close, window=5)

        valid = rsi.dropna()
        assert (valid >= 0.0).all()
        assert (valid <= 100.0).all()


# ---------------------------------------------------------------------------
# RSI property-based tests (Hypothesis)
# ---------------------------------------------------------------------------


@settings(max_examples=60, deadline=None)
@given(
    prices=st.lists(
        st.floats(min_value=0.01, max_value=10_000.0, allow_nan=False, allow_infinity=False),
        min_size=15,
        max_size=100,
    ),
    window=st.integers(min_value=2, max_value=14),
)
def test_hypothesis_rsi_always_in_0_to_100_range(prices: list[float], window: int) -> None:
    close = pd.Series(prices)

    _, rsi = calculate_rs_rsi(close, window=window)

    valid = rsi.dropna()
    assert (valid >= 0.0).all(), f"RSI below 0: {valid[valid < 0.0].tolist()}"
    assert (valid <= 100.0).all(), f"RSI above 100: {valid[valid > 100.0].tolist()}"


# ---------------------------------------------------------------------------
# MACD edge cases
# ---------------------------------------------------------------------------


class TestCalculateMacdEdgeCases:
    def test_empty_series_returns_three_empty_series(self) -> None:
        macd, signal, hist = calculate_macd(pd.Series([], dtype=float))

        assert len(macd) == len(signal) == len(hist) == 0

    def test_single_element_series(self) -> None:
        macd, signal, hist = calculate_macd(pd.Series([100.0]))

        assert len(macd) == len(signal) == len(hist) == 1

    def test_all_nan_series_produces_all_nan(self) -> None:
        macd, signal, hist = calculate_macd(pd.Series([float("nan")] * 30))

        assert macd.isna().all()
        assert hist.isna().all()

    def test_histogram_equals_macd_minus_signal_algebraic_identity(self) -> None:
        close = pd.Series([float(i) for i in range(50)])

        macd, signal, hist = calculate_macd(close)

        pd.testing.assert_series_equal(hist, macd - signal, check_names=False)

    def test_pos_inf_values_do_not_raise(self) -> None:
        close = pd.Series([100.0] * 20 + [float("inf")] + [100.0] * 20)

        macd, signal, hist = calculate_macd(close)

        assert len(macd) == 41

    def test_neg_inf_values_do_not_raise(self) -> None:
        close = pd.Series([100.0] * 20 + [float("-inf")] + [100.0] * 20)

        macd, signal, hist = calculate_macd(close)

        assert len(macd) == 41

    def test_very_large_values_do_not_raise(self) -> None:
        close = pd.Series([1e200 + float(i) for i in range(50)])

        macd, signal, hist = calculate_macd(close)

        assert len(macd) == 50

    def test_very_small_values_do_not_raise(self) -> None:
        close = pd.Series([1e-200 + float(i) * 1e-202 for i in range(50)])

        macd, signal, hist = calculate_macd(close)

        assert len(macd) == 50

    def test_output_lengths_match_input(self) -> None:
        close = pd.Series(range(40))

        macd, signal, hist = calculate_macd(close)

        assert len(macd) == len(signal) == len(hist) == 40

    def test_constant_series_macd_is_zero(self) -> None:
        # EMA12 == EMA26 for a constant series, so MACD must be identically 0.
        close = pd.Series([100.0] * 50)

        macd, signal, hist = calculate_macd(close)

        assert np.allclose(macd.values, 0.0, atol=1e-9)


# ---------------------------------------------------------------------------
# Bollinger Bands edge cases
# ---------------------------------------------------------------------------


class TestCalculateBollingerBandsEdgeCases:
    def test_empty_series_returns_three_empty_series(self) -> None:
        lower, middle, upper = calculate_bollinger_bands(pd.Series([], dtype=float))

        assert len(lower) == len(middle) == len(upper) == 0

    def test_constant_prices_zero_std_gives_equal_bands(self) -> None:
        close = pd.Series([100.0] * 25)

        lower, middle, upper = calculate_bollinger_bands(close, window=20)

        valid_middle = middle.dropna()
        assert np.allclose(valid_middle.values, 100.0, atol=1e-9)
        # Zero std → upper == lower == middle
        pd.testing.assert_series_equal(lower.dropna(), upper.dropna(), check_names=False)

    def test_inf_values_do_not_raise(self) -> None:
        close = pd.Series([100.0] * 15 + [float("inf")] + [100.0] * 9)

        lower, middle, upper = calculate_bollinger_bands(close, window=10)

        assert len(lower) == 25

    def test_upper_band_always_ge_lower_band(self) -> None:
        rng = np.random.default_rng(99)
        close = pd.Series(100.0 + np.cumsum(rng.normal(0, 1, 60)))

        lower, middle, upper = calculate_bollinger_bands(close, window=20)

        valid = ~(lower.isna() | upper.isna())
        assert (upper[valid] >= lower[valid]).all()

    def test_middle_band_is_rolling_mean(self) -> None:
        rng = np.random.default_rng(7)
        close = pd.Series(100.0 + np.cumsum(rng.normal(0, 0.5, 50)))

        _lower, middle, _upper = calculate_bollinger_bands(close, window=20)
        expected_middle = close.rolling(window=20).mean()

        pd.testing.assert_series_equal(middle, expected_middle, check_names=False)


# ---------------------------------------------------------------------------
# add_trend_features edge cases
# ---------------------------------------------------------------------------


class TestAddTrendFeaturesEdgeCases:
    def test_empty_dataframe_returns_expected_columns(self) -> None:
        df = pd.DataFrame(
            {
                "Close": pd.Series([], dtype=float),
                "Volume": pd.Series([], dtype=float),
            }
        )

        out = add_trend_features(df)

        for col in ("MA20", "MA50", "MA200", "RS", "RSI14", "MACD", "MACDSignal", "MACDHist", "DailyReturnPct"):
            assert col in out.columns

    def test_inf_in_close_does_not_produce_inf_in_ma(self) -> None:
        # inf at last row; earlier valid rows should still yield finite MAs.
        close_values = [100.0] * 219 + [float("inf")]
        df = pd.DataFrame({"Close": close_values})

        out = add_trend_features(df)

        # All non-NaN MA20 values should be finite (inf coerced before rolling).
        valid_ma20 = out["MA20"].dropna()
        assert valid_ma20.apply(math.isfinite).all()

    def test_original_dataframe_is_not_mutated(self) -> None:
        df = pd.DataFrame({"Close": [100.0, float("inf"), 102.0]})
        original_close = df["Close"].copy()

        add_trend_features(df)

        pd.testing.assert_series_equal(df["Close"], original_close)
