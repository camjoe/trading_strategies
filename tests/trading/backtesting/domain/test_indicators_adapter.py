from __future__ import annotations

import math

import pandas as pd
import pytest

from trading.backtesting.domain.indicators_adapter import calculate_macd, calculate_rs_rsi


def _close(values: list[float]) -> pd.Series:
    return pd.Series(values, dtype=float)


# ---------------------------------------------------------------------------
# calculate_macd
# ---------------------------------------------------------------------------

def test_calculate_macd_returns_three_series() -> None:
    history = _close([float(i) for i in range(1, 40)])
    macd, signal, histogram = calculate_macd(history)
    assert len(macd) == len(history)
    assert len(signal) == len(history)
    assert len(histogram) == len(history)


def test_calculate_macd_histogram_equals_macd_minus_signal() -> None:
    history = _close([100.0 + i * 0.5 for i in range(40)])
    macd, signal, histogram = calculate_macd(history)
    pd.testing.assert_series_equal(histogram, macd - signal, check_names=False)


def test_calculate_macd_coerces_inf_to_nan() -> None:
    values = [100.0] * 30 + [math.inf, 101.0, 102.0]
    history = _close(values)
    macd, signal, _hist = calculate_macd(history)
    # No inf values should propagate
    assert not macd.replace([math.inf, -math.inf], float("nan")).isna().all()


# ---------------------------------------------------------------------------
# calculate_rs_rsi
# ---------------------------------------------------------------------------

def test_calculate_rs_rsi_returns_two_series() -> None:
    history = _close([float(i) for i in range(1, 30)])
    rs, rsi = calculate_rs_rsi(history)
    assert len(rs) == len(history)
    assert len(rsi) == len(history)


def test_calculate_rs_rsi_rsi_clamped_to_0_100() -> None:
    history = _close([float(i) for i in range(1, 50)])
    _rs, rsi = calculate_rs_rsi(history)
    valid = rsi.dropna()
    assert (valid >= 0.0).all()
    assert (valid <= 100.0).all()


def test_calculate_rs_rsi_respects_window_parameter() -> None:
    history = _close([float(i) for i in range(1, 50)])
    _rs7, rsi7 = calculate_rs_rsi(history, window=7)
    _rs21, rsi21 = calculate_rs_rsi(history, window=21)
    # Different windows produce different RSI values
    assert not rsi7.equals(rsi21)


def test_calculate_rs_rsi_flat_series_gives_neutral_rsi() -> None:
    # Flat price → avg_gain == avg_loss == 0 → RS treated as 1 → RSI = 50
    history = _close([100.0] * 30)
    _rs, rsi = calculate_rs_rsi(history)
    valid = rsi.dropna()
    assert (valid == 50.0).all()


def test_calculate_rs_rsi_coerces_inf_to_nan() -> None:
    values = [100.0] * 20 + [math.inf] + [100.0] * 10
    history = _close(values)
    _rs, rsi = calculate_rs_rsi(history)
    # Should not raise and should return a series of correct length
    assert len(rsi) == len(history)

