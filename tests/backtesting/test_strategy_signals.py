from __future__ import annotations

import pandas as pd
import pytest

from trading.backtesting import strategy_signals


def test_resolve_signal_trend_buy() -> None:
    history = pd.Series([float(i) for i in range(1, 40)])
    assert strategy_signals.resolve_signal("trend_v1", history) == "buy"


def test_resolve_signal_mean_reversion_sell() -> None:
    history = pd.Series([100.0] * 29 + [120.0])
    assert strategy_signals.resolve_signal("mean_reversion", history) == "sell"


def test_resolve_signal_rsi_buy_on_oversold() -> None:
    history = pd.Series([100.0 - float(i) for i in range(40)])
    assert strategy_signals.resolve_signal("rsi_strategy", history) == "buy"


def test_resolve_signal_macd_crossover_buy(monkeypatch: pytest.MonkeyPatch) -> None:
    history = pd.Series([float(i) for i in range(1, 50)])

    macd = pd.Series([0.0] * 48 + [1.0])
    macd_signal = pd.Series([0.0] * 47 + [0.5, 0.2])
    macd_hist = macd - macd_signal

    monkeypatch.setattr(strategy_signals, "calculate_macd", lambda _history: (macd, macd_signal, macd_hist))

    assert strategy_signals.resolve_signal("macd_strategy", history) == "buy"


def test_resolve_signal_default_hold_when_short_history() -> None:
    history = pd.Series([1.0, 2.0, 3.0])
    assert strategy_signals.resolve_signal("unknown_strategy", history) == "hold"
