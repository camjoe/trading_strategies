"""The fixture catalog resolves by id and rejects unknown ids."""

from __future__ import annotations

import pytest

from backtesting.domain.scenario_bench.fixtures import (
    FIXTURE_DEFINITIONS,
    available_fixture_ids,
    fixture_definition,
)
from trading.domain.exceptions import ValidationError


class TestFixtureDefinitions:
    def test_available_ids_are_sorted(self) -> None:
        assert available_fixture_ids() == sorted(FIXTURE_DEFINITIONS)

    def test_resolves_a_known_fixture(self) -> None:
        definition = fixture_definition("covid_crash_2020")
        assert definition.benchmark == "SPY"
        assert definition.tickers

    def test_unknown_fixture_raises(self) -> None:
        with pytest.raises(ValidationError, match="Unknown fixture"):
            fixture_definition("no_such_fixture")
