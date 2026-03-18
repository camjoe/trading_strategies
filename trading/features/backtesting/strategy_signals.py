from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any, Callable, Mapping

import pandas as pd

try:
    from trends.indicators import calculate_macd, calculate_rs_rsi
except ModuleNotFoundError:
    indicators = importlib.import_module("indicators")
    calculate_macd = indicators.calculate_macd
    calculate_rs_rsi = indicators.calculate_rs_rsi


StrategyParams = Mapping[str, Any]
SignalFunction = Callable[[pd.Series, StrategyParams, pd.DataFrame | None], str]


@dataclass(frozen=True)
class StrategySpec:
    strategy_id: str
    signal_fn: SignalFunction
    default_params: dict[str, Any]
    aliases: tuple[str, ...] = ()
    description: str = ""
    required_features: tuple[str, ...] = ()


def _feature_value(feature_history: pd.DataFrame | None, column: str) -> float | None:
    if feature_history is None or feature_history.empty or column not in feature_history.columns:
        return None
    series = pd.to_numeric(feature_history[column], errors="coerce").dropna()
    if series.empty:
        return None
    return float(series.iloc[-1])


def _trend_signal(history: pd.Series, params: StrategyParams, _feature_history: pd.DataFrame | None = None) -> str:
    fast_window = int(params.get("fast_window", 10))
    slow_window = int(params.get("slow_window", 20))
    min_history = max(30, slow_window)
    if len(history) < min_history:
        return "hold"

    close = float(history.iloc[-1])
    sma_fast = float(history.tail(fast_window).mean())
    sma_slow = float(history.tail(slow_window).mean())
    if close > sma_fast > sma_slow:
        return "buy"
    if close < sma_fast:
        return "sell"
    return "hold"


def _mean_reversion_signal(history: pd.Series, params: StrategyParams, _feature_history: pd.DataFrame | None = None) -> str:
    window = int(params.get("window", 20))
    band_pct = float(params.get("band_pct", 0.02))
    if len(history) < 30:
        return "hold"

    close = float(history.iloc[-1])
    sma_mid = float(history.tail(window).mean())
    if close < (sma_mid * (1.0 - band_pct)):
        return "buy"
    if close > (sma_mid * (1.0 + band_pct)):
        return "sell"
    return "hold"


def _rsi_signal(history: pd.Series, params: StrategyParams, _feature_history: pd.DataFrame | None = None) -> str:
    window = int(params.get("window", 14))
    oversold = float(params.get("oversold", 30))
    overbought = float(params.get("overbought", 70))
    min_history = max(30, window + 1)
    if len(history) < min_history:
        return "hold"

    _rs, rsi = calculate_rs_rsi(history, window=window)
    last_rsi = float(rsi.iloc[-1]) if pd.notna(rsi.iloc[-1]) else float("nan")
    if pd.isna(last_rsi):
        return "hold"
    if last_rsi < oversold:
        return "buy"
    if last_rsi > overbought:
        return "sell"
    return "hold"


def _macd_signal(history: pd.Series, _params: StrategyParams, _feature_history: pd.DataFrame | None = None) -> str:
    if len(history) < 35:
        return "hold"

    macd, macd_signal, _hist = calculate_macd(history)
    prev_diff = macd.iloc[-2] - macd_signal.iloc[-2]
    curr_diff = macd.iloc[-1] - macd_signal.iloc[-1]
    if pd.isna(prev_diff) or pd.isna(curr_diff):
        return "hold"
    if prev_diff <= 0 and curr_diff > 0:
        return "buy"
    if prev_diff >= 0 and curr_diff < 0:
        return "sell"
    return "hold"


def _breakout_signal(history: pd.Series, params: StrategyParams, _feature_history: pd.DataFrame | None = None) -> str:
    window = int(params.get("window", 20))
    min_history = max(30, window + 1)
    if len(history) < min_history:
        return "hold"

    current_close = float(history.iloc[-1])
    prior_window = history.iloc[-(window + 1):-1]
    highest_breakout = float(prior_window.max())
    lowest_breakdown = float(prior_window.min())

    if current_close > highest_breakout:
        return "buy"
    if current_close < lowest_breakdown:
        return "sell"
    return "hold"


def _pullback_in_trend_signal(history: pd.Series, params: StrategyParams, _feature_history: pd.DataFrame | None = None) -> str:
    fast_window = int(params.get("fast_window", 20))
    trend_window = int(params.get("trend_window", 50))
    pullback_pct = float(params.get("pullback_pct", 0.03))
    min_history = max(60, trend_window)
    if len(history) < min_history:
        return "hold"

    close = float(history.iloc[-1])
    sma_fast = float(history.tail(fast_window).mean())
    sma_trend = float(history.tail(trend_window).mean())

    if close < sma_trend:
        return "sell"

    in_uptrend = sma_fast > sma_trend
    in_pullback_zone = (sma_fast * (1.0 - pullback_pct)) <= close <= sma_fast
    if in_uptrend and in_pullback_zone:
        return "buy"
    return "hold"


def _bollinger_mean_reversion_signal(history: pd.Series, params: StrategyParams, _feature_history: pd.DataFrame | None = None) -> str:
    window = int(params.get("window", 20))
    num_std = float(params.get("num_std", 2.0))
    min_history = max(30, window)
    if len(history) < min_history:
        return "hold"

    segment = history.tail(window)
    close = float(segment.iloc[-1])
    middle = float(segment.mean())
    std = float(segment.std(ddof=0))
    if std <= 0:
        return "hold"

    lower_band = middle - (num_std * std)
    upper_band = middle + (num_std * std)
    if close < lower_band:
        return "buy"
    if close > upper_band:
        return "sell"
    return "hold"


def _ma_crossover_signal(history: pd.Series, params: StrategyParams, _feature_history: pd.DataFrame | None = None) -> str:
    fast_window = int(params.get("fast_window", 20))
    slow_window = int(params.get("slow_window", 50))
    min_history = max(60, slow_window + 1)
    if len(history) < min_history:
        return "hold"

    fast = history.rolling(window=fast_window).mean()
    slow = history.rolling(window=slow_window).mean()
    prev_fast = float(fast.iloc[-2])
    prev_slow = float(slow.iloc[-2])
    curr_fast = float(fast.iloc[-1])
    curr_slow = float(slow.iloc[-1])

    if pd.isna(prev_fast) or pd.isna(prev_slow) or pd.isna(curr_fast) or pd.isna(curr_slow):
        return "hold"

    if prev_fast <= prev_slow and curr_fast > curr_slow:
        return "buy"
    if prev_fast >= prev_slow and curr_fast < curr_slow:
        return "sell"

    # Keep this strategy actionable after a recent crossover by honoring
    # the current fast/slow stack and price confirmation.
    close = float(history.iloc[-1])
    if curr_fast > curr_slow and close >= curr_fast:
        return "buy"
    if curr_fast < curr_slow and close <= curr_fast:
        return "sell"
    return "hold"


def _volatility_filtered_trend_signal(history: pd.Series, params: StrategyParams, _feature_history: pd.DataFrame | None = None) -> str:
    fast_window = int(params.get("fast_window", 20))
    slow_window = int(params.get("slow_window", 50))
    vol_window = int(params.get("vol_window", 20))
    max_annualized_vol_pct = float(params.get("max_annualized_vol_pct", 45.0))
    min_history = max(60, slow_window, vol_window + 1)
    if len(history) < min_history:
        return "hold"

    returns = history.pct_change().dropna()
    recent_returns = returns.tail(vol_window)
    if recent_returns.empty:
        return "hold"
    annualized_vol_pct = float(recent_returns.std(ddof=0) * (252 ** 0.5) * 100.0)
    if pd.isna(annualized_vol_pct) or annualized_vol_pct > max_annualized_vol_pct:
        return "hold"

    close = float(history.iloc[-1])
    sma_fast = float(history.tail(fast_window).mean())
    sma_slow = float(history.tail(slow_window).mean())
    if close > sma_fast > sma_slow:
        return "buy"
    if close < sma_fast:
        return "sell"
    return "hold"


def _topic_proxy_rotation_signal(
    history: pd.Series,
    params: StrategyParams,
    feature_history: pd.DataFrame | None = None,
) -> str:
    window = int(params.get("window", 20))
    min_history = max(40, window)
    if len(history) < min_history:
        return "hold"

    proxy_available = _feature_value(feature_history, "topic_proxy_available")
    rel_strength = _feature_value(feature_history, "topic_proxy_rel_strength")
    trend_gap = _feature_value(feature_history, "topic_proxy_trend_gap")
    if proxy_available is None or proxy_available < 0.5 or rel_strength is None or trend_gap is None:
        return "hold"

    close = float(history.iloc[-1])
    sma_mid = float(history.tail(window).mean())
    min_rel_strength = float(params.get("min_rel_strength", 0.0))
    exit_rel_strength = float(params.get("exit_rel_strength", 0.0))
    min_proxy_trend_gap = float(params.get("min_proxy_trend_gap", 0.0))

    if close > sma_mid and rel_strength > min_rel_strength and trend_gap > min_proxy_trend_gap:
        return "buy"
    if close < sma_mid or rel_strength < exit_rel_strength or trend_gap < 0.0:
        return "sell"
    return "hold"


def _macro_proxy_regime_signal(
    history: pd.Series,
    params: StrategyParams,
    feature_history: pd.DataFrame | None = None,
) -> str:
    fast_window = int(params.get("fast_window", 20))
    slow_window = int(params.get("slow_window", 50))
    min_history = max(60, slow_window)
    if len(history) < min_history:
        return "hold"

    risk_on_score = _feature_value(feature_history, "macro_risk_on_score")
    vix_pressure = _feature_value(feature_history, "macro_vix_pressure")
    equity_bond_spread = _feature_value(feature_history, "macro_equity_bond_spread")
    if risk_on_score is None or vix_pressure is None or equity_bond_spread is None:
        return "hold"

    close = float(history.iloc[-1])
    sma_fast = float(history.tail(fast_window).mean())
    sma_slow = float(history.tail(slow_window).mean())
    min_risk_on_score = float(params.get("min_risk_on_score", 0.0))
    min_equity_bond_spread = float(params.get("min_equity_bond_spread", 0.0))
    max_vix_pressure = float(params.get("max_vix_pressure", 0.12))
    exit_risk_on_score = float(params.get("exit_risk_on_score", 0.0))

    if (
        close > sma_fast > sma_slow
        and risk_on_score >= min_risk_on_score
        and equity_bond_spread >= min_equity_bond_spread
        and vix_pressure <= max_vix_pressure
    ):
        return "buy"
    if close < sma_fast or risk_on_score < exit_risk_on_score or vix_pressure > max_vix_pressure:
        return "sell"
    return "hold"


STRATEGY_REGISTRY: dict[str, StrategySpec] = {
    "trend": StrategySpec(
        strategy_id="trend",
        signal_fn=_trend_signal,
        default_params={"fast_window": 10, "slow_window": 20},
        aliases=("trend_v1", "momentum"),
        description="Trend stack using close > SMA fast > SMA slow.",
    ),
    "mean_reversion": StrategySpec(
        strategy_id="mean_reversion",
        signal_fn=_mean_reversion_signal,
        default_params={"window": 20, "band_pct": 0.02},
        aliases=("mean", "reversion"),
        description="Mean reversion to SMA with symmetric percentage bands.",
    ),
    "rsi": StrategySpec(
        strategy_id="rsi",
        signal_fn=_rsi_signal,
        default_params={"window": 14, "oversold": 30, "overbought": 70},
        aliases=("rsi_strategy",),
        description="RSI threshold strategy.",
    ),
    "macd": StrategySpec(
        strategy_id="macd",
        signal_fn=_macd_signal,
        default_params={},
        aliases=("macd_strategy",),
        description="MACD crossover strategy.",
    ),
    "breakout": StrategySpec(
        strategy_id="breakout",
        signal_fn=_breakout_signal,
        default_params={"window": 20},
        aliases=("donchian",),
        description="Donchian-style breakout and breakdown signal.",
    ),
    "pullback_trend": StrategySpec(
        strategy_id="pullback_trend",
        signal_fn=_pullback_in_trend_signal,
        default_params={"fast_window": 20, "trend_window": 50, "pullback_pct": 0.03},
        aliases=("pullback",),
        description="Buy pullbacks in a broader uptrend.",
    ),
    "bollinger_mean_reversion": StrategySpec(
        strategy_id="bollinger_mean_reversion",
        signal_fn=_bollinger_mean_reversion_signal,
        default_params={"window": 20, "num_std": 2.0},
        aliases=("bollinger", "bbands"),
        description="Mean reversion using Bollinger bands.",
    ),
    "ma_crossover": StrategySpec(
        strategy_id="ma_crossover",
        signal_fn=_ma_crossover_signal,
        default_params={"fast_window": 20, "slow_window": 50},
        aliases=("moving_average", "ma"),
        description="Fast/slow moving-average crossover.",
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
    ),
    "topic_proxy_rotation": StrategySpec(
        strategy_id="topic_proxy_rotation",
        signal_fn=_topic_proxy_rotation_signal,
        default_params={
            "window": 20,
            "min_rel_strength": 0.0,
            "exit_rel_strength": 0.0,
            "min_proxy_trend_gap": 0.0,
        },
        aliases=("topic_rotation", "sector_proxy_rotation", "theme_proxy"),
        description="Rotate into names backed by strong sector/theme ETF proxy relative strength.",
        required_features=("topic_proxy_rel_strength", "topic_proxy_trend_gap"),
    ),
    "macro_proxy_regime": StrategySpec(
        strategy_id="macro_proxy_regime",
        signal_fn=_macro_proxy_regime_signal,
        default_params={
            "fast_window": 20,
            "slow_window": 50,
            "min_risk_on_score": 0.0,
            "min_equity_bond_spread": 0.0,
            "max_vix_pressure": 0.12,
            "exit_risk_on_score": 0.0,
        },
        aliases=("macro_proxy", "policy_proxy", "macro_risk"),
        description="Use market-risk proxies like VIX and bond-vs-equity leadership as a macro regime filter.",
        required_features=("macro_risk_on_score", "macro_vix_pressure", "macro_equity_bond_spread"),
    ),
}


def available_strategy_ids() -> list[str]:
    return sorted(STRATEGY_REGISTRY.keys())


def _resolve_by_keyword(name: str) -> StrategySpec:
    if any(token in name for token in ("bollinger", "bbands")):
        return STRATEGY_REGISTRY["bollinger_mean_reversion"]
    if "breakout" in name or "donchian" in name:
        return STRATEGY_REGISTRY["breakout"]
    if "pullback" in name:
        return STRATEGY_REGISTRY["pullback_trend"]
    if "vol" in name and "trend" in name:
        return STRATEGY_REGISTRY["volatility_filtered_trend"]
    if "topic" in name or ("sector" in name and "rotation" in name) or "theme" in name:
        return STRATEGY_REGISTRY["topic_proxy_rotation"]
    if "macro" in name or "policy" in name:
        return STRATEGY_REGISTRY["macro_proxy_regime"]
    if "cross" in name and ("ma" in name or "moving_average" in name):
        return STRATEGY_REGISTRY["ma_crossover"]
    if "rsi" in name:
        return STRATEGY_REGISTRY["rsi"]
    if "macd" in name:
        return STRATEGY_REGISTRY["macd"]
    if "mean" in name or "reversion" in name:
        return STRATEGY_REGISTRY["mean_reversion"]
    if "trend" in name or "momentum" in name:
        return STRATEGY_REGISTRY["trend"]
    return STRATEGY_REGISTRY["trend"]


def resolve_strategy(strategy_name: str) -> StrategySpec:
    """Resolve a strategy label to a registry-backed strategy specification."""
    name = strategy_name.strip().lower()
    if name in STRATEGY_REGISTRY:
        return STRATEGY_REGISTRY[name]

    for spec in STRATEGY_REGISTRY.values():
        if name in spec.aliases:
            return spec

    return _resolve_by_keyword(name)


def resolve_signal(
    strategy_name: str,
    history: pd.Series,
    feature_history: pd.DataFrame | None = None,
) -> str:
    """Resolve strategy labels to explicit signal models used during backtesting."""
    spec = resolve_strategy(strategy_name)
    return spec.signal_fn(history, spec.default_params, feature_history)
