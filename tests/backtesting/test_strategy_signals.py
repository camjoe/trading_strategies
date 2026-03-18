from __future__ import annotations

import pandas as pd
import pytest

from trading.backtesting import strategy_signals


def _series_range(start: int, stop: int) -> pd.Series:
    return pd.Series([float(i) for i in range(start, stop)])


def test_resolve_signal_trend_buy() -> None:
    history = _series_range(1, 40)
    assert strategy_signals.resolve_signal("trend_v1", history) == "buy"


def test_resolve_signal_mean_reversion_sell() -> None:
    history = pd.Series([100.0] * 29 + [120.0])
    assert strategy_signals.resolve_signal("mean_reversion", history) == "sell"


def test_resolve_signal_rsi_buy_on_oversold() -> None:
    history = pd.Series([100.0 - float(i) for i in range(40)])
    assert strategy_signals.resolve_signal("rsi_strategy", history) == "buy"


def test_resolve_signal_macd_crossover_buy(monkeypatch: pytest.MonkeyPatch) -> None:
    history = _series_range(1, 50)

    macd = pd.Series([0.0] * 48 + [1.0])
    macd_signal = pd.Series([0.0] * 47 + [0.5, 0.2])
    macd_hist = macd - macd_signal

    monkeypatch.setattr(strategy_signals, "calculate_macd", lambda _history: (macd, macd_signal, macd_hist))

    assert strategy_signals.resolve_signal("macd_strategy", history) == "buy"


def test_resolve_signal_default_hold_when_short_history() -> None:
    history = pd.Series([1.0, 2.0, 3.0])
    assert strategy_signals.resolve_signal("unknown_strategy", history) == "hold"


def test_available_strategy_ids_include_phase2_families() -> None:
    ids = set(strategy_signals.available_strategy_ids())
    assert "breakout" in ids
    assert "pullback_trend" in ids
    assert "bollinger_mean_reversion" in ids
    assert "ma_crossover" in ids
    assert "volatility_filtered_trend" in ids
    assert "topic_proxy_rotation" in ids
    assert "macro_proxy_regime" in ids


def test_resolve_strategy_exact_and_keyword_aliases() -> None:
    assert strategy_signals.resolve_strategy("breakout").strategy_id == "breakout"
    assert strategy_signals.resolve_strategy("donchian_push").strategy_id == "breakout"
    assert strategy_signals.resolve_strategy("bollinger_band_v1").strategy_id == "bollinger_mean_reversion"
    assert strategy_signals.resolve_strategy("sector_rotation_proxy").strategy_id == "topic_proxy_rotation"
    assert strategy_signals.resolve_strategy("policy_proxy").strategy_id == "macro_proxy_regime"
    assert strategy_signals.resolve_strategy("unknown").strategy_id == "trend"


def test_resolve_signal_breakout_buy() -> None:
    history = pd.Series([100.0 + float(i) for i in range(40)])
    assert strategy_signals.resolve_signal("breakout", history) == "buy"


def test_resolve_signal_bollinger_mean_reversion_buy() -> None:
    history = pd.Series([100.0] * 39 + [80.0])
    assert strategy_signals.resolve_signal("bollinger_mean_reversion", history) == "buy"


def test_resolve_signal_ma_crossover_buy() -> None:
    history = pd.Series([100.0] * 55 + [101.0, 102.0, 103.0, 104.0, 105.0])
    assert strategy_signals.resolve_signal("ma_crossover", history) == "buy"


def test_resolve_signal_volatility_filtered_trend_holds_when_vol_too_high() -> None:
    history = pd.Series([100.0 + ((-1.0) ** i) * (i * 1.2) for i in range(80)])
    assert strategy_signals.resolve_signal("volatility_filtered_trend", history) == "hold"


def test_resolve_signal_topic_proxy_rotation_buy() -> None:
    history = pd.Series([100.0 + (i * 0.7) for i in range(45)])
    feature_history = pd.DataFrame(
        {
            "topic_proxy_available": [1.0] * 45,
            "topic_proxy_rel_strength": [0.01] * 45,
            "topic_proxy_trend_gap": [0.02] * 45,
        },
        index=pd.date_range("2026-01-01", periods=45, freq="B"),
    )

    assert strategy_signals.resolve_signal("topic_proxy_rotation", history, feature_history) == "buy"


def test_resolve_signal_topic_proxy_rotation_holds_without_proxy_features() -> None:
    history = pd.Series([100.0 + (i * 0.7) for i in range(45)])
    assert strategy_signals.resolve_signal("topic_proxy_rotation", history) == "hold"


def test_resolve_signal_macro_proxy_regime_sell_on_risk_off() -> None:
    history = pd.Series([100.0 + (i * 0.5) for i in range(65)])
    feature_history = pd.DataFrame(
        {
            "macro_risk_on_score": [-0.2] * 65,
            "macro_vix_pressure": [0.25] * 65,
            "macro_equity_bond_spread": [-0.05] * 65,
        },
        index=pd.date_range("2026-01-01", periods=65, freq="B"),
    )

    assert strategy_signals.resolve_signal("macro_proxy_regime", history, feature_history) == "sell"
