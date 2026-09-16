"""Declared real-history episodes the bench can replay or bootstrap.

One definition per episode: the tickers, the benchmark, and the date range to
capture. Both the capture script and the scenario registry read this, so an
episode is described in exactly one place. The captured bars live untracked under
``local/scenario_bench/`` — Yahoo data is not redistributed in the repository, so
each operator captures once with ``scripts.data_ops.capture_scenario_fixture``.
"""

from __future__ import annotations

from dataclasses import dataclass

from trading.domain.exceptions import ValidationError

# A small, liquid, cross-sector basket. Not advice — an illustrative universe so a
# bench result is about strategy behavior, not a particular stock pick.
_DEFAULT_BASKET = ("AAPL", "MSFT", "AMZN", "JPM", "XOM", "JNJ")
_DEFAULT_BENCHMARK = "SPY"


@dataclass(frozen=True)
class FixtureDefinition:
    """What to capture for one real-history episode."""

    fixture_id: str
    tickers: tuple[str, ...]
    benchmark: str
    start: str
    end: str
    description: str


FIXTURE_DEFINITIONS: dict[str, FixtureDefinition] = {
    "covid_crash_2020": FixtureDefinition(
        fixture_id="covid_crash_2020",
        tickers=_DEFAULT_BASKET,
        benchmark=_DEFAULT_BENCHMARK,
        start="2020-01-02",
        end="2020-06-30",
        description="The February-March 2020 crash and the recovery into mid-year.",
    ),
    "bear_2022": FixtureDefinition(
        fixture_id="bear_2022",
        tickers=_DEFAULT_BASKET,
        benchmark=_DEFAULT_BENCHMARK,
        start="2022-01-03",
        end="2022-10-31",
        description="The 2022 rate-hike bear market drawdown.",
    ),
    "grind_2017": FixtureDefinition(
        fixture_id="grind_2017",
        tickers=_DEFAULT_BASKET,
        benchmark=_DEFAULT_BENCHMARK,
        start="2017-01-03",
        end="2017-12-29",
        description="The low-volatility upward grind of 2017.",
    ),
}


def available_fixture_ids() -> list[str]:
    return sorted(FIXTURE_DEFINITIONS.keys())


def fixture_definition(fixture_id: str) -> FixtureDefinition:
    definition = FIXTURE_DEFINITIONS.get(fixture_id)
    if definition is None:
        available = ", ".join(available_fixture_ids())
        raise ValidationError(f"Unknown fixture '{fixture_id}'. Valid fixtures: {available}")
    return definition
