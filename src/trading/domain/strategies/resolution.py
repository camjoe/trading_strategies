from __future__ import annotations

import pandas as pd

from trading.domain.exceptions import ValidationError
from trading.domain.strategies.contracts import StrategyParams, StrategySpec
from trading.domain.strategies.registry import STRATEGY_REGISTRY, available_strategy_ids


def _invalid_strategy_error(strategy_name: str) -> ValueError:
    available = ", ".join(available_strategy_ids())
    return ValidationError(f"Unknown strategy '{strategy_name}'. Valid strategies: {available}")


def _resolve_exact_or_alias(name: str) -> StrategySpec | None:
    if name in STRATEGY_REGISTRY:
        return STRATEGY_REGISTRY[name]

    for spec in STRATEGY_REGISTRY.values():
        if name in spec.aliases:
            return spec

    return None


def _resolve_by_keyword(name: str) -> StrategySpec | None:
    if any(token in name for token in ("bollinger", "bbands")):
        return STRATEGY_REGISTRY["bollinger_mean_reversion"]
    if "breakout" in name or "donchian" in name:
        return STRATEGY_REGISTRY["breakout"]
    if "pullback" in name:
        return STRATEGY_REGISTRY["pullback_trend"]
    if "vol" in name and "trend" in name:
        return STRATEGY_REGISTRY["volatility_filtered_trend"]
    if "cross" in name and ("ma" in name or "moving_average" in name):
        return STRATEGY_REGISTRY["ma_crossover"]
    if "rsi" in name:
        return STRATEGY_REGISTRY["rsi"]
    if "mean" in name or "reversion" in name:
        return STRATEGY_REGISTRY["mean_reversion"]
    if "trend" in name or "momentum" in name:
        return STRATEGY_REGISTRY["trend"]
    return None


def resolve_strategy(strategy_name: str) -> StrategySpec:
    """Resolve a strategy label to a registry-backed strategy specification."""
    name = strategy_name.strip().lower()
    if not name:
        raise _invalid_strategy_error(strategy_name)

    exact_match = _resolve_exact_or_alias(name)
    if exact_match is not None:
        return exact_match

    keyword_match = _resolve_by_keyword(name)
    if keyword_match is not None:
        return keyword_match

    raise _invalid_strategy_error(strategy_name)


def validate_strategy_name(strategy_name: str) -> str:
    """Validate an operator-provided strategy label and return its canonical strategy id."""
    return resolve_strategy(strategy_name).strategy_id


def evaluate_signal(
    strategy_name: str,
    history: pd.Series,
    params: StrategyParams,
    feature_history: pd.DataFrame | None = None,
) -> str:
    """Evaluate a strategy's signal with explicit params — the shared backtest/live entry."""
    spec = resolve_strategy(strategy_name)
    return spec.signal_fn(history, params, feature_history)


def resolve_signal(
    strategy_name: str,
    history: pd.Series,
    feature_history: pd.DataFrame | None = None,
) -> str:
    """Resolve strategy labels to explicit signal models evaluated with default params."""
    spec = resolve_strategy(strategy_name)
    return evaluate_signal(strategy_name, history, spec.default_params, feature_history)
