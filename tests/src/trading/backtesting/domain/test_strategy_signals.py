from __future__ import annotations

import random

import pandas as pd
import pytest
from hypothesis import given, settings, strategies as st

from trading.domain.strategies import indicator_view, resolution
from trading.domain.strategies.registry import available_strategy_ids


def _series_range(start: int, stop: int) -> pd.Series:
    return pd.Series([float(i) for i in range(start, stop)])


def _series_steady(length: int = 80, base: float = 100.0, step: float = 0.1) -> pd.Series:
    """Steady upward series long enough for all strategy min-history thresholds."""
    return pd.Series([base + float(i) * step for i in range(length)])


def _assert_signal(
    strategy_name: str,
    history: pd.Series,
    expected: str,
    feature_history: pd.DataFrame | None = None,
) -> None:
    assert resolution.resolve_signal(strategy_name, history, feature_history) == expected


def test_available_strategy_ids_include_expanded_families() -> None:
    ids = set(available_strategy_ids())
    assert "breakout" in ids
    assert "pullback_trend" in ids
    assert "bollinger_mean_reversion" in ids
    assert "ma_crossover" in ids
    assert "volatility_filtered_trend" in ids


def test_resolve_strategy_exact_and_keyword_aliases() -> None:
    assert resolution.resolve_strategy("breakout").strategy_id == "breakout"
    assert resolution.resolve_strategy("donchian_push").strategy_id == "breakout"
    assert resolution.resolve_strategy("bollinger_band_v1").strategy_id == "bollinger_mean_reversion"

    with pytest.raises(ValueError, match="Unknown strategy 'unknown'"):
        resolution.resolve_strategy("unknown")


def test_resolve_strategy_trims_and_uses_aliases() -> None:
    assert resolution.resolve_strategy("  MA  ").strategy_id == "ma_crossover"
    assert resolution.resolve_strategy("VOL_FILTER_TREND").strategy_id == "volatility_filtered_trend"


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
        indicator_view,
        "calculate_rs_rsi",
        lambda _history, window=14: (pd.Series([1.0] * len(history)), pd.Series([80.0] * len(history))),
    )
    _assert_signal("rsi", history, "sell")

    monkeypatch.setattr(
        indicator_view,
        "calculate_rs_rsi",
        lambda _history, window=14: (pd.Series([1.0] * len(history)), pd.Series([float("nan")] * len(history))),
    )
    _assert_signal("rsi", history, "hold")


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


def test_default_hold_when_short_history() -> None:
    history = pd.Series([1.0, 2.0, 3.0])
    _assert_signal("trend", history, "hold")


def test_resolve_signal_rejects_unknown_strategy_name() -> None:
    with pytest.raises(ValueError, match="Unknown strategy 'unknown_strategy'"):
        resolution.resolve_signal("unknown_strategy", _series_range(1, 40))


def test_evaluate_signal_explicit_params_override_defaults() -> None:
    history = _series_range(1, 40)
    spec = resolution.resolve_strategy("trend")

    default_signal = resolution.evaluate_signal_over_history("trend", history, spec.default_params)
    assert default_signal == resolution.resolve_signal("trend", history) == "buy"

    # Swapping the windows inverts the SMA relationship, so explicit params flip buy → hold.
    overridden = resolution.evaluate_signal_over_history("trend", history, {"fast_window": 20, "slow_window": 10})
    assert overridden == "hold"


def test_evaluate_signal_rejects_unknown_strategy_name() -> None:
    with pytest.raises(ValueError, match="Unknown strategy 'unknown_strategy'"):
        resolution.evaluate_signal_over_history("unknown_strategy", _series_range(1, 40), {})


def test_fuzz_resolve_signal_outputs_known_actions() -> None:
    rng = random.Random(42)
    strategies = available_strategy_ids()

    for strategy_id in strategies:
        for _ in range(25):
            length = rng.randint(30, 90)
            price = 100.0
            values: list[float] = []
            for _i in range(length):
                price += rng.uniform(-2.0, 2.0)
                values.append(price)

            history = pd.Series(values)
            signal = resolution.resolve_signal(strategy_id, history)
            assert signal in {"buy", "sell", "hold"}


@settings(max_examples=30, deadline=None)
@given(
    strategy_id=st.sampled_from(
        [
            "trend",
            "mean_reversion",
            "rsi",
            "breakout",
            "pullback_trend",
            "bollinger_mean_reversion",
            "ma_crossover",
            "volatility_filtered_trend",
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
    signal = resolution.resolve_signal(strategy_id, history)
    assert signal in {"buy", "sell", "hold"}


# ---------------------------------------------------------------------------
# Inf / NaN guard regression tests
# ---------------------------------------------------------------------------


class TestSignalInfAtLastPositionReturnsHold:
    """Strategies with explicit close guards must return 'hold' when the most
    recent price is non-finite, not a spurious buy/sell based on garbage data."""

    @pytest.mark.parametrize(
        "strategy_id",
        ["trend", "mean_reversion", "breakout", "bollinger_mean_reversion"],
    )
    def test_pos_inf_close_returns_hold(self, strategy_id: str) -> None:
        history = _series_steady()
        history.iloc[-1] = float("inf")

        signal = resolution.resolve_signal(strategy_id, history)

        assert signal == "hold"

    @pytest.mark.parametrize(
        "strategy_id",
        ["trend", "mean_reversion", "breakout", "bollinger_mean_reversion"],
    )
    def test_neg_inf_close_returns_hold(self, strategy_id: str) -> None:
        history = _series_steady()
        history.iloc[-1] = float("-inf")

        signal = resolution.resolve_signal(strategy_id, history)

        assert signal == "hold"

    def test_inf_close_returns_hold_for_pullback_trend(self) -> None:
        history = _series_steady(length=80)
        history.iloc[-1] = float("inf")

        assert resolution.resolve_signal("pullback_trend", history) == "hold"

    def test_inf_close_returns_hold_for_ma_crossover(self) -> None:
        history = _series_steady(length=80)
        history.iloc[-1] = float("inf")

        assert resolution.resolve_signal("ma_crossover", history) == "hold"

    def test_inf_close_returns_hold_for_volatility_filtered_trend(self) -> None:
        history = _series_steady(length=80)
        history.iloc[-1] = float("inf")

        assert resolution.resolve_signal("volatility_filtered_trend", history) == "hold"


class TestSignalInfInSmaWindowReturnsHold:
    """When inf contaminates a recent SMA window (but NOT the last price), signal
    functions that guard SMAs must return 'hold' rather than a spurious buy/sell."""

    def test_inf_in_trend_sma_window_returns_hold(self) -> None:
        # Close is finite (200.0), but inf at -5 lands inside both SMA windows.
        history = _series_steady(length=80, base=100.0)
        history.iloc[-5] = float("inf")

        assert resolution.resolve_signal("trend", history) == "hold"

    def test_inf_in_mean_reversion_sma_window_returns_hold(self) -> None:
        # Without the sma_mid guard: sma_mid = inf → close < inf → spurious "buy".
        history = pd.Series([100.0] * 79 + [80.0])
        history.iloc[-15] = float("inf")

        assert resolution.resolve_signal("mean_reversion", history) == "hold"

    def test_inf_in_breakout_prior_window_returns_hold(self) -> None:
        history = _series_steady(length=80, base=100.0)
        history.iloc[-10] = float("inf")

        assert resolution.resolve_signal("breakout", history) == "hold"

    def test_inf_in_ma_crossover_window_returns_hold(self) -> None:
        history = _series_steady(length=80, base=100.0)
        history.iloc[-10] = float("inf")

        assert resolution.resolve_signal("ma_crossover", history) == "hold"


class TestFeatureValueInfGuard:
    """_feature_value must treat inf feature values as unavailable → 'hold'."""


@settings(max_examples=30, deadline=None)
@given(
    strategy_id=st.sampled_from(
        [
            "trend",
            "mean_reversion",
            "rsi",
            "breakout",
            "pullback_trend",
            "bollinger_mean_reversion",
            "ma_crossover",
            "volatility_filtered_trend",
        ]
    ),
    history_values=st.lists(
        st.floats(min_value=1.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
        min_size=30,
        max_size=90,
    ),
    inf_positions=st.lists(st.integers(min_value=0, max_value=89), min_size=0, max_size=3),
)
def test_hypothesis_inf_in_history_never_raises(
    strategy_id: str,
    history_values: list[float],
    inf_positions: list[int],
) -> None:
    history = pd.Series(history_values)
    for pos in inf_positions:
        if pos < len(history):
            history.iloc[pos] = float("inf")

    # Must not raise; output must be a valid signal token.
    signal = resolution.resolve_signal(strategy_id, history)
    assert signal in {"buy", "sell", "hold"}


# ---------------------------------------------------------------------------
# Short-history hold guards for individual strategies
# ---------------------------------------------------------------------------


def test_short_history_hold_for_rsi() -> None:
    _assert_signal("rsi", pd.Series([100.0, 101.0, 102.0]), "hold")


def test_short_history_hold_for_breakout() -> None:
    _assert_signal("breakout", pd.Series([100.0, 101.0, 102.0]), "hold")


def test_short_history_hold_for_bollinger() -> None:
    _assert_signal("bollinger_mean_reversion", pd.Series([100.0, 101.0, 102.0]), "hold")


# ---------------------------------------------------------------------------
# MA crossover: exact golden/death cross entries
# ---------------------------------------------------------------------------


def test_ma_crossover_golden_cross_returns_buy() -> None:
    """Fast MA just crossed above slow MA → buy (line 276).

    59 flat points at 100.0 then a slight uptick forces fast MA to rise above
    slow MA on the last bar while both were equal on the prior bar.
    """
    _assert_signal("ma_crossover", pd.Series([100.0] * 59 + [100.1]), "buy")


def test_ma_crossover_death_cross_returns_sell() -> None:
    """Fast MA just crossed below slow MA → sell (line 278)."""
    _assert_signal("ma_crossover", pd.Series([100.0] * 59 + [99.9]), "sell")


# ---------------------------------------------------------------------------
# Volatility-filtered trend: non-finite recent-returns and SMA guards
# ---------------------------------------------------------------------------


def test_volatility_filtered_trend_empty_recent_returns_returns_hold() -> None:
    """All pct_change values are NaN (inf history) → returns empty → 'hold' (line 313)."""
    _assert_signal("volatility_filtered_trend", pd.Series([float("inf")] * 60 + [100.0]), "hold")


def test_volatility_filtered_trend_inf_in_slow_sma_window_returns_hold() -> None:
    """Inf inside the slow-SMA window makes sma_slow non-finite → 'hold' (line 322)."""
    _assert_signal(
        "volatility_filtered_trend",
        pd.Series([100.0] * 40 + [float("inf")] + [100.0] * 21),
        "hold",
    )


class TestResolveByKeyword:
    """Keyword-resolver branches are only reached when the name is not a known exact key or alias.
    Use names that contain the keyword but are not registered aliases."""

    def test_pullback_keyword_resolves(self) -> None:
        assert resolution.resolve_strategy("pullback_v2").strategy_id == "pullback_trend"

    def test_vol_trend_keyword_resolves(self) -> None:
        assert resolution.resolve_strategy("vol_trend_v2").strategy_id == "volatility_filtered_trend"

    def test_cross_ma_keyword_resolves(self) -> None:
        assert resolution.resolve_strategy("cross_ma_v3").strategy_id == "ma_crossover"

    def test_rsi_keyword_resolves(self) -> None:
        assert resolution.resolve_strategy("custom_rsi_v2").strategy_id == "rsi"

    def test_mean_reversion_keyword_resolves(self) -> None:
        assert resolution.resolve_strategy("mean_custom_v2").strategy_id == "mean_reversion"

    def test_trend_keyword_resolves(self) -> None:
        assert resolution.resolve_strategy("fast_trend_v3").strategy_id == "trend"

    def test_unknown_keyword_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Unknown strategy"):
            resolution.resolve_strategy("unknown_xyz_v99")
