"""Compatibility shim for the decomposed strategy package.

The strategy code moved into ``trading.domain.strategies`` — split by responsibility
into ``contracts``, ``signals`` (``technical``/``alternative``), ``registry``,
``parameter_validation``, and ``resolution``. This module re-exports the public API
and the signal internals that existing callers and tests import, so imports of
``trading.domain.strategy_signals`` keep working. New code should import from the
concrete ``trading.domain.strategies.*`` modules directly.
"""

from __future__ import annotations

from trading.domain.strategies.contracts import (  # noqa: F401
    PrimitiveSpec,
    SignalFunction,
    StrategyParams,
    StrategySpec,
)
from trading.domain.strategies.parameter_validation import (  # noqa: F401
    _coerce_float_knob,
    _coerce_int_knob,
    _coerce_knob_value,
    resolve_primitive,
    validate_params_against_primitive,
)
from trading.domain.strategies.registry import (  # noqa: F401
    PRIMITIVE_CATALOG,
    STRATEGY_REGISTRY,
    available_strategy_ids,
)
from trading.domain.strategies.resolution import (  # noqa: F401
    _invalid_strategy_error,
    _resolve_by_keyword,
    _resolve_exact_or_alias,
    evaluate_signal,
    resolve_signal,
    resolve_strategy,
    validate_strategy_name,
)
from trading.domain.strategies.signals.alternative import (  # noqa: F401
    PROXY_AVAILABILITY_THRESHOLD,
    _feature_value,
    _macro_proxy_regime_signal,
    _news_sentiment_signal,
    _policy_regime_signal,
    _social_trend_rotation_signal,
    _topic_proxy_rotation_signal,
)
from trading.domain.strategies.signals.technical import (  # noqa: F401
    _bollinger_mean_reversion_signal,
    _breakout_signal,
    _ma_crossover_signal,
    _macd_signal,
    _mean_reversion_signal,
    _pullback_in_trend_signal,
    _rsi_signal,
    _trend_signal,
    _volatility_filtered_trend_signal,
)
