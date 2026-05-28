"""Re-export shim — canonical location is trading.domain.strategy_signals."""

from trading.domain.strategy_signals import (
    PROXY_AVAILABILITY_THRESHOLD,
    STRATEGY_REGISTRY,
    SignalFunction,
    StrategyParams,
    StrategySpec,
    available_strategy_ids,
    resolve_signal,
    resolve_strategy,
    validate_strategy_name,
)

__all__ = [
    "PROXY_AVAILABILITY_THRESHOLD",
    "STRATEGY_REGISTRY",
    "SignalFunction",
    "StrategyParams",
    "StrategySpec",
    "available_strategy_ids",
    "resolve_signal",
    "resolve_strategy",
    "validate_strategy_name",
]
