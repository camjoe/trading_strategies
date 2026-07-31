from __future__ import annotations

from common.constants import RSI_DEFAULT_WINDOW, RSI_OVERBOUGHT, RSI_OVERSOLD
from trading.domain.strategies.contracts import PrimitiveSpec, StrategySpec
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
        aliases=("trend_v1", "momentum"),
        description="Trend stack using close > SMA fast > SMA slow.",
        strategy_style="trend",
    ),
    "mean_reversion": StrategySpec(
        strategy_id="mean_reversion",
        signal_fn=_mean_reversion_signal,
        default_params={"window": 20, "band_pct": 0.02},
        aliases=("mean", "reversion"),
        description="Mean reversion to SMA with symmetric percentage bands.",
        strategy_style="mean_reversion",
    ),
    "rsi": StrategySpec(
        strategy_id="rsi",
        signal_fn=_rsi_signal,
        default_params={"window": RSI_DEFAULT_WINDOW, "oversold": RSI_OVERSOLD, "overbought": RSI_OVERBOUGHT},
        aliases=("rsi_strategy",),
        description="RSI threshold strategy.",
        strategy_style="mean_reversion",
    ),
    "breakout": StrategySpec(
        strategy_id="breakout",
        signal_fn=_breakout_signal,
        default_params={"window": 20},
        aliases=("donchian",),
        description="Donchian-style breakout and breakdown signal.",
        strategy_style="trend",
    ),
    "pullback_trend": StrategySpec(
        strategy_id="pullback_trend",
        signal_fn=_pullback_in_trend_signal,
        default_params={"fast_window": 20, "trend_window": 50, "pullback_pct": 0.03},
        aliases=("pullback",),
        description="Buy pullbacks in a broader uptrend.",
        strategy_style="trend",
    ),
    "bollinger_mean_reversion": StrategySpec(
        strategy_id="bollinger_mean_reversion",
        signal_fn=_bollinger_mean_reversion_signal,
        default_params={"window": 20, "num_std": 2.0},
        aliases=("bollinger", "bbands"),
        description="Mean reversion using Bollinger bands.",
        strategy_style="mean_reversion",
    ),
    "ma_crossover": StrategySpec(
        strategy_id="ma_crossover",
        signal_fn=_ma_crossover_signal,
        default_params={"fast_window": 20, "slow_window": 50},
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
