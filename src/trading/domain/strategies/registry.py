from __future__ import annotations

from common.constants import RSI_DEFAULT_WINDOW, RSI_OVERBOUGHT, RSI_OVERSOLD
from trading.domain.strategies.contracts import (
    INDICATOR_KIND_RETURN_VOL,
    INDICATOR_KIND_ROLLING_MAX,
    INDICATOR_KIND_ROLLING_MIN,
    INDICATOR_KIND_RSI,
    INDICATOR_KIND_SMA,
    INDICATOR_KIND_STDDEV,
    IndicatorSpec,
    PrimitiveSpec,
    StrategySpec,
)
from trading.domain.strategies.signals.technical import (
    _bollinger_mean_reversion_signal,
    _breakout_signal,
    _ma_crossover_signal,
    _mean_reversion_signal,
    _pullback_in_trend_signal,
    _rsi_signal,
    _trend_signal,
    _volatility_filtered_trend_signal,
)

STRATEGY_REGISTRY: dict[str, StrategySpec] = {
    "trend": StrategySpec(
        strategy_id="trend",
        signal_fn=_trend_signal,
        default_params={"fast_window": 10, "slow_window": 20},
        indicators=(
            IndicatorSpec("fast_ma", INDICATOR_KIND_SMA, window_param="fast_window", default_window=10),
            IndicatorSpec("slow_ma", INDICATOR_KIND_SMA, window_param="slow_window", default_window=20),
        ),
        aliases=("trend_v1", "momentum"),
        description="Trend stack using close > SMA fast > SMA slow.",
        strategy_style="trend",
    ),
    "mean_reversion": StrategySpec(
        strategy_id="mean_reversion",
        signal_fn=_mean_reversion_signal,
        default_params={"window": 20, "band_pct": 0.02},
        indicators=(IndicatorSpec("mid_ma", INDICATOR_KIND_SMA, window_param="window", default_window=20),),
        aliases=("mean", "reversion"),
        description="Mean reversion to SMA with symmetric percentage bands.",
        strategy_style="mean_reversion",
    ),
    "rsi": StrategySpec(
        strategy_id="rsi",
        signal_fn=_rsi_signal,
        default_params={"window": RSI_DEFAULT_WINDOW, "oversold": RSI_OVERSOLD, "overbought": RSI_OVERBOUGHT},
        indicators=(
            IndicatorSpec("rsi", INDICATOR_KIND_RSI, window_param="window", default_window=RSI_DEFAULT_WINDOW),
        ),
        aliases=("rsi_strategy",),
        description="RSI threshold strategy.",
        strategy_style="mean_reversion",
    ),
    "breakout": StrategySpec(
        strategy_id="breakout",
        signal_fn=_breakout_signal,
        default_params={"window": 20},
        # Sourced from close, matching the behaviour this replaces. A breakout is
        # properly defined on the prior window's true highs and lows; switching
        # the source waits until the live path also reads bars.
        indicators=(
            IndicatorSpec("prior_high", INDICATOR_KIND_ROLLING_MAX, window_param="window", default_window=20, shift=1),
            IndicatorSpec("prior_low", INDICATOR_KIND_ROLLING_MIN, window_param="window", default_window=20, shift=1),
        ),
        aliases=("donchian",),
        description="Donchian-style breakout and breakdown signal.",
        strategy_style="trend",
    ),
    "pullback_trend": StrategySpec(
        strategy_id="pullback_trend",
        signal_fn=_pullback_in_trend_signal,
        default_params={"fast_window": 20, "trend_window": 50, "pullback_pct": 0.03},
        indicators=(
            IndicatorSpec("fast_ma", INDICATOR_KIND_SMA, window_param="fast_window", default_window=20),
            IndicatorSpec("trend_ma", INDICATOR_KIND_SMA, window_param="trend_window", default_window=50),
        ),
        aliases=("pullback",),
        description="Buy pullbacks in a broader uptrend.",
        strategy_style="trend",
    ),
    "bollinger_mean_reversion": StrategySpec(
        strategy_id="bollinger_mean_reversion",
        signal_fn=_bollinger_mean_reversion_signal,
        default_params={"window": 20, "num_std": 2.0},
        indicators=(
            IndicatorSpec("mid_ma", INDICATOR_KIND_SMA, window_param="window", default_window=20),
            IndicatorSpec("band_std", INDICATOR_KIND_STDDEV, window_param="window", default_window=20),
        ),
        aliases=("bollinger", "bbands"),
        description="Mean reversion using Bollinger bands.",
        strategy_style="mean_reversion",
    ),
    "ma_crossover": StrategySpec(
        strategy_id="ma_crossover",
        signal_fn=_ma_crossover_signal,
        default_params={"fast_window": 20, "slow_window": 50},
        indicators=(
            IndicatorSpec("fast_ma", INDICATOR_KIND_SMA, window_param="fast_window", default_window=20),
            IndicatorSpec("slow_ma", INDICATOR_KIND_SMA, window_param="slow_window", default_window=50),
        ),
        aliases=("moving_average", "ma"),
        description="Fast/slow moving-average crossover.",
        strategy_style="trend",
    ),
    "volatility_filtered_trend": StrategySpec(
        strategy_id="volatility_filtered_trend",
        signal_fn=_volatility_filtered_trend_signal,
        default_params={
            "fast_window": 20,
            "slow_window": 50,
            "vol_window": 20,
            "max_annualized_vol_pct": 45.0,
        },
        indicators=(
            IndicatorSpec("fast_ma", INDICATOR_KIND_SMA, window_param="fast_window", default_window=20),
            IndicatorSpec("slow_ma", INDICATOR_KIND_SMA, window_param="slow_window", default_window=50),
            IndicatorSpec("return_vol", INDICATOR_KIND_RETURN_VOL, window_param="vol_window", default_window=20),
        ),
        aliases=("volatility_trend", "vol_filter_trend"),
        description="Trend signal only when recent annualized volatility is below threshold.",
        strategy_style="trend",
    ),
}


def available_strategy_ids() -> list[str]:
    return sorted(STRATEGY_REGISTRY.keys())


# One primitive per registered signal function today; keyed by the registry
# strategy id, which doubles as the primitive name for the seeded catalog.
PRIMITIVE_CATALOG: dict[str, PrimitiveSpec] = {
    spec.strategy_id: PrimitiveSpec(
        primitive=spec.strategy_id,
        signal_fn=spec.signal_fn,
        knob_schema=dict(spec.default_params),
        style=spec.strategy_style,
        required_features=spec.required_features,
        description=spec.description,
    )
    for spec in STRATEGY_REGISTRY.values()
}
