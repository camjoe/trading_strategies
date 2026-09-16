"""The scenario catalog: one declarative entry per named market condition.

This is the single place to look for what the bench can run, and the single place
to add a scenario. A synthetic scenario is one entry that names a generator and
its parameters; a new regime *shape* is one function in ``generators.py`` that an
entry then references. The benchmark shares each scenario's regime, so it is
priced by the same generator over the same window.
"""

from __future__ import annotations

from trading.domain.exceptions import ValidationError

from .contracts import SCENARIO_MODE_BOOTSTRAP, SCENARIO_MODE_REPLAY, FixtureSource, ScenarioSpec
from .fixtures import FIXTURE_DEFINITIONS, available_fixture_ids
from .generators import gbm_regime, regime_switch, unbound_generator

# One trading year of daily bars for the standard scenarios.
_ONE_YEAR_DAYS = 252
# One half-year, for the fast crash scenarios.
_HALF_YEAR_DAYS = 126

# Bootstrap resample length. Replay length comes from the fixture and overrides
# this placeholder at bind time.
_BOOTSTRAP_DAYS = _HALF_YEAR_DAYS
_REPLAY_PLACEHOLDER_DAYS = _ONE_YEAR_DAYS
# Base seed for the first real-data scenario; each fixture takes a 10-wide band so
# replay and bootstrap of the same fixture never share a seed.
_REAL_SCENARIO_SEED_BASE = 3000

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


def _register_real_scenarios() -> None:
    """Add a replay and a bootstrap scenario for every declared fixture.

    Real-data scenarios carry the unbound generator sentinel and a `FixtureSource`;
    the composition seam loads the fixture and binds the real generator at run time.
    Deriving both from one fixture definition keeps a new episode to a single entry
    in `fixtures.py`.
    """
    for index, fixture_id in enumerate(available_fixture_ids()):
        definition = FIXTURE_DEFINITIONS[fixture_id]
        seed_base = _REAL_SCENARIO_SEED_BASE + index * 10
        SCENARIO_REGISTRY[f"{fixture_id}_replay"] = ScenarioSpec(
            scenario_id=f"{fixture_id}_replay",
            generator=unbound_generator,
            params={},
            path_count=1,
            tickers=definition.tickers,
            benchmark=definition.benchmark,
            base_seed=seed_base,
            days=_REPLAY_PLACEHOLDER_DAYS,
            description=f"Replay of real history: {definition.description}",
            source=FixtureSource(fixture_id=fixture_id, mode=SCENARIO_MODE_REPLAY),
        )
        SCENARIO_REGISTRY[f"{fixture_id}_bootstrap"] = ScenarioSpec(
            scenario_id=f"{fixture_id}_bootstrap",
            generator=unbound_generator,
            params={},
            path_count=200,
            tickers=definition.tickers,
            benchmark=definition.benchmark,
            base_seed=seed_base + 1,
            days=_BOOTSTRAP_DAYS,
            description=f"Block bootstrap of real history: {definition.description}",
            source=FixtureSource(fixture_id=fixture_id, mode=SCENARIO_MODE_BOOTSTRAP),
        )


_register_real_scenarios()


def available_scenario_ids() -> list[str]:
    """The registered scenario ids, sorted."""
    return sorted(SCENARIO_REGISTRY.keys())


def default_scenario_ids() -> list[str]:
    """The scenario ids that run offline with no captured fixture (the synthetic set).

    The default run uses these so `backtest-bench` works with no setup. Real-data
    scenarios need a captured fixture, so they are opt-in by name.
    """
    return sorted(scenario_id for scenario_id, spec in SCENARIO_REGISTRY.items() if spec.source is None)


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
