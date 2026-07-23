from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

import pandas as pd

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
