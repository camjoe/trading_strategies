from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Mapping

import pandas as pd

if TYPE_CHECKING:
    from trading.domain.strategies.indicator_view import IndicatorView

StrategyParams = Mapping[str, Any]
# A signal reads its indicators from a view positioned at one bar — not from a
# price history it derives them from itself. `IndicatorView` is imported lazily
# under TYPE_CHECKING because it imports this module for the indicator kinds.
SignalFunction = Callable[["IndicatorView", StrategyParams, "pd.DataFrame | None"], str]

# Bar columns an indicator can be computed over. Mirrors
# ``trading.models.market_data.constants`` without importing it, so the strategy
# contract stays free of a data-layer dependency.
INDICATOR_SOURCE_OPEN = "open"
INDICATOR_SOURCE_HIGH = "high"
INDICATOR_SOURCE_LOW = "low"
INDICATOR_SOURCE_CLOSE = "close"

# Supported indicator computations. Each is a rolling window over one bar column.
INDICATOR_KIND_SMA = "sma"
INDICATOR_KIND_ROLLING_MAX = "rolling_max"
INDICATOR_KIND_ROLLING_MIN = "rolling_min"
INDICATOR_KIND_STDDEV = "stddev"
INDICATOR_KIND_RSI = "rsi"
INDICATOR_KIND_RETURN_VOL = "return_vol"


@dataclass(frozen=True)
class IndicatorSpec:
    """One series a strategy reads, declared so the engine can precompute it.

    The engine computes each declared indicator once per ticker per run and
    hands the signal the values for the current bar. Without the declaration a
    signal has to derive its own indicator from a price history on every bar,
    which is the same rolling window recomputed from scratch for every trading
    day — quadratic work to produce one number.

    ``window_param`` names the knob that sets the window, so an optimizer
    sweeping that knob changes the indicator rather than being ignored;
    ``default_window`` applies when the knob is absent.

    ``shift`` lags the series by N bars. A breakout compares today's price
    against the highest high of the *prior* window, so it declares ``shift=1``
    to exclude the bar being decided — without it the comparison includes the
    value it is testing and can never fire.
    """

    name: str
    kind: str
    source: str = INDICATOR_SOURCE_CLOSE
    window_param: str | None = None
    default_window: int | None = None
    shift: int = 0

    def window_for(self, params: StrategyParams) -> int:
        """The effective window under *params*."""
        if self.window_param is not None:
            configured = params.get(self.window_param)
            if configured is not None:
                return int(configured)
        if self.default_window is None:
            raise ValueError(f"Indicator '{self.name}' has neither a configured window nor a default.")
        return int(self.default_window)


@dataclass(frozen=True)
class StrategySpec:
    strategy_id: str
    signal_fn: SignalFunction
    default_params: dict[str, Any]
    # Series the engine precomputes once per ticker per run and exposes to the
    # signal through an IndicatorView. Empty means the signal derives everything
    # itself from the price history it is handed.
    indicators: tuple[IndicatorSpec, ...] = ()
    aliases: tuple[str, ...] = ()
    description: str = ""
    required_features: tuple[str, ...] = ()
    # Broad behavioral family: "trend", "mean_reversion", "neutral", or "alternative".
    # Used by policy layers to set sell bias and other style-dependent behavior
    # without resorting to fragile string matching on strategy names.
    # "alternative" = external-data-driven strategies (news, social, policy);
    # see repo-root features/ for the provider infrastructure.
    strategy_style: str = "neutral"


@dataclass(frozen=True)
class PrimitiveSpec:
    """A code signal primitive: the tested signal function plus its knob schema.

    The code half of the strategy = primitive + knobs model. A `strategies`
    row binds one primitive to a concrete knob dict; the knob schema here is the
    primitive's tunable knob names with their code defaults.
    """

    primitive: str
    signal_fn: SignalFunction
    knob_schema: Mapping[str, Any]
    style: str
    required_features: tuple[str, ...] = ()
    description: str = ""
