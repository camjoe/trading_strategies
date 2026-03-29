from __future__ import annotations

import random

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from trading.backtesting.domain import strategy_signals


def _series_range(start: int, stop: int) -> pd.Series:
    return pd.Series([float(i) for i in range(start, stop)])


def _feature_history(**columns: list[float]) -> pd.DataFrame:
    first_column = next(iter(columns.values()))
    return pd.DataFrame(
        columns,
        index=pd.date_range("2026-01-01", periods=len(first_column), freq="B"),
    )


def _assert_signal(
    strategy_name: str,
    history: pd.Series,
    expected: str,
    feature_history: pd.DataFrame | None = None,
) -> None:
    assert strategy_signals.resolve_signal(strategy_name, history, feature_history) == expected


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


def test_resolve_strategy_trims_and_uses_aliases() -> None:
    assert strategy_signals.resolve_strategy("  MA  ").strategy_id == "ma_crossover"
    assert strategy_signals.resolve_strategy("VOL_FILTER_TREND").strategy_id == "volatility_filtered_trend"


def test_trend_buy_sell_hold() -> None:
    _assert_signal("trend_v1", _series_range(1, 40), "buy")
    _assert_signal("trend", pd.Series([100.0] * 39 + [90.0]), "sell")
    _assert_signal("trend", pd.Series([100.0] * 40), "hold")


def test_mean_reversion_buy_sell_hold() -> None:
    _assert_signal("mean_reversion", pd.Series([100.0] * 29 + [70.0]), "buy")
    _assert_signal("mean_reversion", pd.Series([100.0] * 29 + [120.0]), "sell")
    _assert_signal("mean_reversion", pd.Series([100.0] * 30), "hold")


def test_rsi_buy_sell_and_nan_hold(monkeypatch: pytest.MonkeyPatch) -> None:
    history = pd.Series([100.0 - float(i) for i in range(40)])
    _assert_signal("rsi_strategy", history, "buy")

    history = _series_range(1, 50)
    monkeypatch.setattr(
        strategy_signals,
        "calculate_rs_rsi",
        lambda _history, window=14: (pd.Series([1.0] * len(history)), pd.Series([80.0] * len(history))),
    )
    _assert_signal("rsi", history, "sell")

    monkeypatch.setattr(
        strategy_signals,
        "calculate_rs_rsi",
        lambda _history, window=14: (pd.Series([1.0] * len(history)), pd.Series([float("nan")] * len(history))),
    )
    _assert_signal("rsi", history, "hold")


def test_macd_buy_sell_and_nan_hold(monkeypatch: pytest.MonkeyPatch) -> None:
    history = _series_range(1, 50)

    macd_buy = pd.Series([0.0] * 48 + [1.0])
    macd_signal_buy = pd.Series([0.0] * 47 + [0.5, 0.2])
    monkeypatch.setattr(
        strategy_signals,
        "calculate_macd",
        lambda _history: (macd_buy, macd_signal_buy, macd_buy - macd_signal_buy),
    )
    _assert_signal("macd_strategy", history, "buy")

    macd_sell = pd.Series([0.0] * 47 + [0.5, 0.4, 0.1])
    macd_signal_sell = pd.Series([0.0] * 47 + [0.2, 0.3, 0.2])
    monkeypatch.setattr(
        strategy_signals,
        "calculate_macd",
        lambda _history: (macd_sell, macd_signal_sell, macd_sell - macd_signal_sell),
    )
    _assert_signal("macd", history, "sell")

    macd_nan = pd.Series([0.0] * 48 + [float("nan"), 1.0])
    macd_signal_nan = pd.Series([0.0] * 48 + [0.0, 0.5])
    monkeypatch.setattr(
        strategy_signals,
        "calculate_macd",
        lambda _history: (macd_nan, macd_signal_nan, macd_nan - macd_signal_nan),
    )
    _assert_signal("macd", history, "hold")


def test_breakout_buy_sell_hold() -> None:
    _assert_signal("breakout", pd.Series([100.0 + float(i) for i in range(40)]), "buy")
    _assert_signal("breakout", pd.Series([120.0 - float(i) for i in range(40)]), "sell")
    _assert_signal("breakout", pd.Series([100.0] * 40), "hold")


def test_pullback_trend_buy_and_sell() -> None:
    _assert_signal("pullback_trend", pd.Series([100.0] * 58 + [108.0, 100.3]), "buy")
    _assert_signal("pullback_trend", pd.Series([100.0] * 58 + [98.0, 95.0]), "sell")


def test_bollinger_buy_sell_and_zero_std_hold() -> None:
    _assert_signal("bollinger_mean_reversion", pd.Series([100.0] * 39 + [80.0]), "buy")
    _assert_signal("bollinger_mean_reversion", pd.Series([100.0] * 39 + [120.0]), "sell")
    _assert_signal("bollinger_mean_reversion", pd.Series([100.0] * 40), "hold")


def test_ma_crossover_buy_sell_and_stack_buy() -> None:
    _assert_signal("ma_crossover", pd.Series([100.0] * 55 + [101.0, 102.0, 103.0, 104.0, 105.0]), "buy")
    _assert_signal("ma_crossover", pd.Series([120.0] * 55 + [119.0, 118.0, 117.0, 116.0, 115.0]), "sell")
    _assert_signal("ma_crossover", pd.Series([100.0] * 55 + [101.0, 101.0, 101.0, 101.0, 101.0]), "buy")


def test_volatility_filtered_trend_buy_sell_and_high_vol_hold() -> None:
    _assert_signal("volatility_filtered_trend", pd.Series([100.0 + (i * 0.2) for i in range(80)]), "buy")
    _assert_signal("volatility_filtered_trend", pd.Series([120.0 - (i * 0.2) for i in range(80)]), "sell")
    _assert_signal(
        "volatility_filtered_trend",
        pd.Series([100.0 + ((-1.0) ** i) * (i * 1.2) for i in range(80)]),
        "hold",
    )


def test_topic_proxy_rotation_buy_hold_and_sell() -> None:
    history = pd.Series([100.0 + (i * 0.7) for i in range(45)])
    buy_features = _feature_history(
        topic_proxy_available=[1.0] * 45,
        topic_proxy_rel_strength=[0.01] * 45,
        topic_proxy_trend_gap=[0.02] * 45,
    )
    sell_features = _feature_history(
        topic_proxy_available=[1.0] * 45,
        topic_proxy_rel_strength=[-0.2] * 45,
        topic_proxy_trend_gap=[-0.1] * 45,
    )

    _assert_signal("topic_proxy_rotation", history, "buy", buy_features)
    _assert_signal("topic_proxy_rotation", history, "sell", sell_features)
    _assert_signal("topic_proxy_rotation", history, "hold")


def test_macro_proxy_regime_buy_sell_and_missing_features_hold() -> None:
    history = pd.Series([100.0 + (i * 0.5) for i in range(65)])
    risk_on_features = _feature_history(
        macro_risk_on_score=[0.2] * 65,
        macro_vix_pressure=[0.05] * 65,
        macro_equity_bond_spread=[0.1] * 65,
    )
    risk_off_features = _feature_history(
        macro_risk_on_score=[-0.2] * 65,
        macro_vix_pressure=[0.25] * 65,
        macro_equity_bond_spread=[-0.05] * 65,
    )
    missing_columns = _feature_history(macro_risk_on_score=[0.2] * 65)

    _assert_signal("macro_proxy_regime", history, "buy", risk_on_features)
    _assert_signal("macro_proxy_regime", history, "sell", risk_off_features)
    _assert_signal("macro_proxy_regime", history, "hold", missing_columns)


def test_default_hold_when_short_history() -> None:
    history = pd.Series([1.0, 2.0, 3.0])
    _assert_signal("unknown_strategy", history, "hold")


def test_fuzz_resolve_signal_outputs_known_actions() -> None:
    rng = random.Random(42)
    strategies = strategy_signals.available_strategy_ids()

    for strategy_id in strategies:
        for _ in range(25):
            length = rng.randint(30, 90)
            price = 100.0
            values: list[float] = []
            for _i in range(length):
                price += rng.uniform(-2.0, 2.0)
                values.append(price)

            history = pd.Series(values)
            features = _feature_history(
                topic_proxy_available=[rng.choice([0.0, 1.0]) for _ in range(length)],
                topic_proxy_rel_strength=[rng.uniform(-0.3, 0.3) for _ in range(length)],
                topic_proxy_trend_gap=[rng.uniform(-0.3, 0.3) for _ in range(length)],
                macro_risk_on_score=[rng.uniform(-0.5, 0.5) for _ in range(length)],
                macro_vix_pressure=[rng.uniform(0.0, 0.4) for _ in range(length)],
                macro_equity_bond_spread=[rng.uniform(-0.2, 0.2) for _ in range(length)],
            )

            signal = strategy_signals.resolve_signal(strategy_id, history, features)
            assert signal in {"buy", "sell", "hold"}


@settings(max_examples=30, deadline=None)
@given(
    strategy_id=st.sampled_from(
        [
            "trend",
            "mean_reversion",
            "rsi",
            "macd",
            "breakout",
            "pullback_trend",
            "bollinger_mean_reversion",
            "ma_crossover",
            "volatility_filtered_trend",
            "topic_proxy_rotation",
            "macro_proxy_regime",
        ]
    ),
    history_values=st.lists(
        st.floats(min_value=1.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
        min_size=30,
        max_size=90,
    ),
)
def test_hypothesis_resolve_signal_outputs_known_actions(
    strategy_id: str,
    history_values: list[float],
) -> None:
    history = pd.Series(history_values)
    length = len(history_values)
    features = _feature_history(
        topic_proxy_available=[1.0] * length,
        topic_proxy_rel_strength=[0.0] * length,
        topic_proxy_trend_gap=[0.0] * length,
        macro_risk_on_score=[0.0] * length,
        macro_vix_pressure=[0.1] * length,
        macro_equity_bond_spread=[0.0] * length,
    )

    signal = strategy_signals.resolve_signal(strategy_id, history, features)
    assert signal in {"buy", "sell", "hold"}
