"""The scenario catalog: one declarative entry per named market condition.

This is the single place to look for what the bench can run, and the single place
to add a scenario. A synthetic scenario is one entry that names a generator and
its parameters; a new regime *shape* is one function in ``generators.py`` that an
entry then references. The benchmark shares each scenario's regime, so it is
priced by the same generator over the same window.
"""

from __future__ import annotations

from trading.domain.exceptions import ValidationError

from .contracts import ScenarioSpec
from .generators import gbm_regime, regime_switch

# One trading year of daily bars for the standard scenarios.
_ONE_YEAR_DAYS = 252
# One half-year, for the fast crash scenarios.
_HALF_YEAR_DAYS = 126

# The synthetic tradable universe. Deliberately small and abstract: these are not
# real symbols, so a bench result can never be mistaken for real-market evidence.
_SYNTHETIC_TICKERS = ("SYN1", "SYN2", "SYN3")
_SYNTHETIC_BENCHMARK = "BENCH"


SCENARIO_REGISTRY: dict[str, ScenarioSpec] = {
    "strong_uptrend": ScenarioSpec(
        scenario_id="strong_uptrend",
        generator=gbm_regime,
        params={"annual_drift": 0.35, "annual_vol": 0.18},
        path_count=200,
        tickers=_SYNTHETIC_TICKERS,
        benchmark=_SYNTHETIC_BENCHMARK,
        base_seed=1001,
        days=_ONE_YEAR_DAYS,
        description="A strong, steady rise over one year.",
        aliases=("uptrend", "bull"),
    ),
    "steady_bull": ScenarioSpec(
        scenario_id="steady_bull",
        generator=gbm_regime,
        params={"annual_drift": 0.12, "annual_vol": 0.12},
        path_count=200,
        tickers=_SYNTHETIC_TICKERS,
        benchmark=_SYNTHETIC_BENCHMARK,
        base_seed=1002,
        days=_ONE_YEAR_DAYS,
        description="A modest rise with low volatility.",
        aliases=("quiet_bull",),
    ),
    "choppy_flat": ScenarioSpec(
        scenario_id="choppy_flat",
        generator=gbm_regime,
        params={"annual_drift": 0.0, "annual_vol": 0.14},
        path_count=200,
        tickers=_SYNTHETIC_TICKERS,
        benchmark=_SYNTHETIC_BENCHMARK,
        base_seed=1003,
        days=_ONE_YEAR_DAYS,
        description="A sideways, directionless market.",
        aliases=("sideways", "chop"),
    ),
    "high_volatility": ScenarioSpec(
        scenario_id="high_volatility",
        generator=gbm_regime,
        params={"annual_drift": 0.0, "annual_vol": 0.55},
        path_count=200,
        tickers=_SYNTHETIC_TICKERS,
        benchmark=_SYNTHETIC_BENCHMARK,
        base_seed=1004,
        days=_ONE_YEAR_DAYS,
        description="No net drift, but violent day-to-day swings.",
        aliases=("volatile", "high_vol"),
    ),
    "sharp_crash": ScenarioSpec(
        scenario_id="sharp_crash",
        generator=gbm_regime,
        params={"annual_drift": -0.9, "annual_vol": 0.5},
        path_count=200,
        tickers=_SYNTHETIC_TICKERS,
        benchmark=_SYNTHETIC_BENCHMARK,
        base_seed=1005,
        days=_HALF_YEAR_DAYS,
        description="A steep broad sell-off over one half-year.",
        aliases=("crash", "bear"),
    ),
    "melt_up_then_crash": ScenarioSpec(
        scenario_id="melt_up_then_crash",
        generator=regime_switch,
        params={
            "phase1_drift": 0.4,
            "phase1_vol": 0.15,
            "phase2_drift": -1.2,
            "phase2_vol": 0.6,
            "switch_fraction": 0.7,
        },
        path_count=200,
        tickers=_SYNTHETIC_TICKERS,
        benchmark=_SYNTHETIC_BENCHMARK,
        base_seed=1006,
        days=_ONE_YEAR_DAYS,
        description="A euphoric rise that reverses into a sharp crash.",
        aliases=("blowoff", "melt_up"),
    ),
}


def available_scenario_ids() -> list[str]:
    """The registered scenario ids, sorted."""
    return sorted(SCENARIO_REGISTRY.keys())


def _invalid_scenario_error(scenario_name: str) -> ValidationError:
    available = ", ".join(available_scenario_ids())
    return ValidationError(f"Unknown scenario '{scenario_name}'. Valid scenarios: {available}")


def resolve_scenario(scenario_name: str) -> ScenarioSpec:
    """Resolve a scenario label to its spec by exact id, then by alias."""
    name = scenario_name.strip().lower()
    if not name:
        raise _invalid_scenario_error(scenario_name)

    if name in SCENARIO_REGISTRY:
        return SCENARIO_REGISTRY[name]

    for spec in SCENARIO_REGISTRY.values():
        if name in spec.aliases:
            return spec

    raise _invalid_scenario_error(scenario_name)
