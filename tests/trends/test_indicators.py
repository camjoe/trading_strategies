import numpy as np
import pandas as pd
import pytest

from trends.indicators import add_trend_features, calculate_macd, calculate_rs_rsi


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
