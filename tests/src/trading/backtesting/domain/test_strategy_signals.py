from __future__ import annotations

import random

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from trading.domain import strategy_signals


def _series_range(start: int, stop: int) -> pd.Series:
    return pd.Series([float(i) for i in range(start, stop)])


def _series_steady(length: int = 80, base: float = 100.0, step: float = 0.1) -> pd.Series:
    """Steady upward series long enough for all strategy min-history thresholds."""
    return pd.Series([base + float(i) * step for i in range(length)])


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


def test_available_strategy_ids_include_expanded_families() -> None:
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

    with pytest.raises(ValueError, match="Unknown strategy 'unknown'"):
        strategy_signals.resolve_strategy("unknown")


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
    _assert_signal("trend", history, "hold")


def test_resolve_signal_rejects_unknown_strategy_name() -> None:
    with pytest.raises(ValueError, match="Unknown strategy 'unknown_strategy'"):
        strategy_signals.resolve_signal("unknown_strategy", _series_range(1, 40))


def test_evaluate_signal_explicit_params_override_defaults() -> None:
    history = _series_range(1, 40)
    spec = strategy_signals.resolve_strategy("trend")

    default_signal = strategy_signals.evaluate_signal("trend", history, spec.default_params)
    assert default_signal == strategy_signals.resolve_signal("trend", history) == "buy"

    # Swapping the windows inverts the SMA relationship, so explicit params flip buy → hold.
    overridden = strategy_signals.evaluate_signal("trend", history, {"fast_window": 20, "slow_window": 10})
    assert overridden == "hold"


def test_evaluate_signal_rejects_unknown_strategy_name() -> None:
    with pytest.raises(ValueError, match="Unknown strategy 'unknown_strategy'"):
        strategy_signals.evaluate_signal("unknown_strategy", _series_range(1, 40), {})


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


# ---------------------------------------------------------------------------
# Inf / NaN guard regression tests
# ---------------------------------------------------------------------------


def _full_features(length: int) -> pd.DataFrame:
    """Feature history with all proxy columns present and well-formed."""
    return _feature_history(
        topic_proxy_available=[1.0] * length,
        topic_proxy_rel_strength=[0.05] * length,
        topic_proxy_trend_gap=[0.05] * length,
        macro_risk_on_score=[0.2] * length,
        macro_vix_pressure=[0.05] * length,
        macro_equity_bond_spread=[0.1] * length,
    )


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

        signal = strategy_signals.resolve_signal(strategy_id, history)

        assert signal == "hold"

    @pytest.mark.parametrize(
        "strategy_id",
        ["trend", "mean_reversion", "breakout", "bollinger_mean_reversion"],
    )
    def test_neg_inf_close_returns_hold(self, strategy_id: str) -> None:
        history = _series_steady()
        history.iloc[-1] = float("-inf")

        signal = strategy_signals.resolve_signal(strategy_id, history)

        assert signal == "hold"

    def test_inf_close_returns_hold_for_pullback_trend(self) -> None:
        history = _series_steady(length=80)
        history.iloc[-1] = float("inf")

        assert strategy_signals.resolve_signal("pullback_trend", history) == "hold"

    def test_inf_close_returns_hold_for_ma_crossover(self) -> None:
        history = _series_steady(length=80)
        history.iloc[-1] = float("inf")

        assert strategy_signals.resolve_signal("ma_crossover", history) == "hold"

    def test_inf_close_returns_hold_for_volatility_filtered_trend(self) -> None:
        history = _series_steady(length=80)
        history.iloc[-1] = float("inf")

        assert strategy_signals.resolve_signal("volatility_filtered_trend", history) == "hold"

    def test_inf_close_returns_hold_for_topic_proxy_rotation(self) -> None:
        history = _series_steady(length=80)
        history.iloc[-1] = float("inf")
        features = _full_features(80)

        assert strategy_signals.resolve_signal("topic_proxy_rotation", history, features) == "hold"

    def test_inf_close_returns_hold_for_macro_proxy_regime(self) -> None:
        history = _series_steady(length=80)
        history.iloc[-1] = float("inf")
        features = _full_features(80)

        assert strategy_signals.resolve_signal("macro_proxy_regime", history, features) == "hold"


class TestSignalInfInSmaWindowReturnsHold:
    """When inf contaminates a recent SMA window (but NOT the last price), signal
    functions that guard SMAs must return 'hold' rather than a spurious buy/sell."""

    def test_inf_in_trend_sma_window_returns_hold(self) -> None:
        # Close is finite (200.0), but inf at -5 lands inside both SMA windows.
        history = _series_steady(length=80, base=100.0)
        history.iloc[-5] = float("inf")

        assert strategy_signals.resolve_signal("trend", history) == "hold"

    def test_inf_in_mean_reversion_sma_window_returns_hold(self) -> None:
        # Without the sma_mid guard: sma_mid = inf → close < inf → spurious "buy".
        history = pd.Series([100.0] * 79 + [80.0])
        history.iloc[-15] = float("inf")

        assert strategy_signals.resolve_signal("mean_reversion", history) == "hold"

    def test_inf_in_breakout_prior_window_returns_hold(self) -> None:
        history = _series_steady(length=80, base=100.0)
        history.iloc[-10] = float("inf")

        assert strategy_signals.resolve_signal("breakout", history) == "hold"

    def test_inf_in_ma_crossover_window_returns_hold(self) -> None:
        history = _series_steady(length=80, base=100.0)
        history.iloc[-10] = float("inf")

        assert strategy_signals.resolve_signal("ma_crossover", history) == "hold"


class TestFeatureValueInfGuard:
    """_feature_value must treat inf feature values as unavailable → 'hold'."""

    def test_inf_proxy_available_treated_as_missing(self) -> None:
        history = _series_steady(length=80, base=100.0, step=0.7)
        features = _feature_history(
            topic_proxy_available=[float("inf")] * 80,
            topic_proxy_rel_strength=[0.05] * 80,
            topic_proxy_trend_gap=[0.05] * 80,
        )

        # proxy_available = inf → treated as None → "hold"
        assert strategy_signals.resolve_signal("topic_proxy_rotation", history, features) == "hold"

    def test_inf_macro_feature_treated_as_missing(self) -> None:
        history = _series_steady(length=80, base=100.0, step=0.5)
        features = _feature_history(
            macro_risk_on_score=[float("inf")] * 80,
            macro_vix_pressure=[0.05] * 80,
            macro_equity_bond_spread=[0.1] * 80,
        )

        # risk_on_score = inf → treated as None → "hold"
        assert strategy_signals.resolve_signal("macro_proxy_regime", history, features) == "hold"


# ---------------------------------------------------------------------------
# Hypothesis: inf/NaN inputs never raise exceptions and produce valid signals
# ---------------------------------------------------------------------------


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
    signal = strategy_signals.resolve_signal(strategy_id, history)
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
# _feature_value: all-NaN column returns None → strategy falls back to "hold"
# ---------------------------------------------------------------------------


def test_feature_value_all_nan_column_falls_back_to_hold() -> None:
    """_feature_value returns None when the column is present but all values are NaN (line 69)."""
    length = 60
    features = _feature_history(
        policy_risk_on_score=[float("nan")] * length,
        policy_defensive_tilt=[0.01] * length,
    )
    _assert_signal("policy_regime", _series_steady(length=length), "hold", features)


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


# ---------------------------------------------------------------------------
# policy_regime: buy and sell paths
# ---------------------------------------------------------------------------


def test_policy_regime_buy_signal() -> None:
    """policy_regime returns 'buy' on uptrend + strong risk-on score + low defensive tilt (lines 453-454)."""
    length = 60
    features = _feature_history(
        policy_risk_on_score=[0.6] * length,  # ≥ POLICY_RISK_ON_BUY_THRESHOLD (0.55)
        policy_defensive_tilt=[0.01] * length,  # ≤ POLICY_MAX_DEFENSIVE_TILT (0.02)
    )
    _assert_signal("policy_regime", _series_steady(length=length), "buy", features)


def test_policy_regime_sell_signal_low_risk_on_score() -> None:
    """policy_regime returns 'sell' when risk_on_score < risk_off_threshold (lines 455-456)."""
    length = 60
    features = _feature_history(
        policy_risk_on_score=[0.3] * length,  # < POLICY_RISK_OFF_SELL_THRESHOLD (0.45)
        policy_defensive_tilt=[0.01] * length,
    )
    _assert_signal("policy_regime", _series_steady(length=length), "sell", features)


# ---------------------------------------------------------------------------
# news_sentiment: missing features, insufficient headlines, buy, sell
# ---------------------------------------------------------------------------


def test_news_sentiment_missing_features_returns_hold() -> None:
    """news_sentiment returns 'hold' when feature_history is None (lines 484-485)."""
    _assert_signal("news_sentiment", _series_steady(length=40), "hold")


def test_news_sentiment_insufficient_headlines_returns_hold() -> None:
    """news_sentiment returns 'hold' when headline_count < min_headlines (lines 487-489)."""
    length = 40
    features = _feature_history(
        news_sentiment_score=[0.5] * length,
        news_headline_count=[1.0] * length,  # < NEWS_MIN_HEADLINES_REQUIRED (3.0)
    )
    _assert_signal("news_sentiment", _series_steady(length=length), "hold", features)


def test_news_sentiment_buy_signal() -> None:
    """news_sentiment returns 'buy' on uptrend + positive sentiment + enough headlines (lines 500-501)."""
    length = 40
    features = _feature_history(
        news_sentiment_score=[0.2] * length,  # ≥ NEWS_BUY_SENTIMENT_THRESHOLD (0.10)
        news_headline_count=[5.0] * length,  # ≥ NEWS_MIN_HEADLINES_REQUIRED (3.0)
    )
    _assert_signal("news_sentiment", _series_steady(length=length), "buy", features)


def test_news_sentiment_sell_signal() -> None:
    """news_sentiment returns 'sell' on close < sma_fast + negative sentiment (lines 502-503)."""
    length = 40
    # Sharp drop at the last bar: close < sma_fast ✓
    history = pd.Series([100.0 + float(i) * 0.5 for i in range(length - 1)] + [50.0])
    features = _feature_history(
        news_sentiment_score=[-0.2] * length,  # ≤ NEWS_SELL_SENTIMENT_THRESHOLD (-0.10)
        news_headline_count=[5.0] * length,
    )
    _assert_signal("news_sentiment", history, "sell", features)


# ---------------------------------------------------------------------------
# social_trend_rotation: short history, buy, sell
# ---------------------------------------------------------------------------


def test_social_trend_rotation_short_history_returns_hold() -> None:
    """social_trend_rotation returns 'hold' when history is too short (line 529)."""
    _assert_signal("social_trend_rotation", pd.Series([100.0, 101.0, 102.0]), "hold")


def test_social_trend_rotation_buy_signal() -> None:
    """social_trend_rotation returns 'buy' on uptrend + high trend_score + positive reddit (lines 553-554)."""
    length = 40
    features = _feature_history(
        social_trend_score=[0.5] * length,  # ≥ SOCIAL_TREND_BUY_THRESHOLD (0.40)
        social_mention_count=[10.0] * length,
        social_reddit_sentiment=[0.0] * length,  # ≥ SOCIAL_MIN_REDDIT_SENTIMENT (-0.05)
    )
    _assert_signal("social_trend_rotation", _series_steady(length=length), "buy", features)


def test_social_trend_rotation_sell_signal_low_trend_score() -> None:
    """social_trend_rotation returns 'sell' when trend_score < trend_exit threshold (lines 555-556)."""
    length = 40
    features = _feature_history(
        social_trend_score=[0.1] * length,  # < SOCIAL_TREND_EXIT_THRESHOLD (0.20)
        social_mention_count=[10.0] * length,
        social_reddit_sentiment=[0.0] * length,
    )
    _assert_signal("social_trend_rotation", _series_steady(length=length), "sell", features)


# ---------------------------------------------------------------------------
# _resolve_by_keyword: each keyword branch + unknown fallback
# ---------------------------------------------------------------------------


class TestResolveByKeyword:
    """Keyword-resolver branches are only reached when the name is not a known exact key or alias.
    Use names that contain the keyword but are not registered aliases."""

    def test_pullback_keyword_resolves(self) -> None:
        assert strategy_signals.resolve_strategy("pullback_v2").strategy_id == "pullback_trend"

    def test_vol_trend_keyword_resolves(self) -> None:
        assert strategy_signals.resolve_strategy("vol_trend_v2").strategy_id == "volatility_filtered_trend"

    def test_policy_regime_keyword_resolves(self) -> None:
        assert strategy_signals.resolve_strategy("my_policy_regime_v2").strategy_id == "policy_regime"

    def test_macro_keyword_resolves(self) -> None:
        assert strategy_signals.resolve_strategy("macro_system_v1").strategy_id == "macro_proxy_regime"

    def test_news_keyword_resolves(self) -> None:
        assert strategy_signals.resolve_strategy("custom_news_model").strategy_id == "news_sentiment"

    def test_social_keyword_resolves(self) -> None:
        assert strategy_signals.resolve_strategy("reddit_v2").strategy_id == "social_trend_rotation"

    def test_cross_ma_keyword_resolves(self) -> None:
        assert strategy_signals.resolve_strategy("cross_ma_v3").strategy_id == "ma_crossover"

    def test_rsi_keyword_resolves(self) -> None:
        assert strategy_signals.resolve_strategy("custom_rsi_v2").strategy_id == "rsi"

    def test_mean_reversion_keyword_resolves(self) -> None:
        assert strategy_signals.resolve_strategy("mean_custom_v2").strategy_id == "mean_reversion"

    def test_trend_keyword_resolves(self) -> None:
        assert strategy_signals.resolve_strategy("fast_trend_v3").strategy_id == "trend"

    def test_unknown_keyword_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Unknown strategy"):
            strategy_signals.resolve_strategy("unknown_xyz_v99")
