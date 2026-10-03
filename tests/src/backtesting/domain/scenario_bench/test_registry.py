"""The catalog must resolve by id and alias, and every entry must generate bars."""

from __future__ import annotations

import pandas as pd
import pytest

from backtesting.domain.scenario_bench.contracts import PathRequest
from backtesting.domain.scenario_bench.registry import (
    SCENARIO_REGISTRY,
    available_scenario_ids,
    resolve_scenario,
)
from trading.domain.exceptions import ValidationError
from trading.models.market_data import BAR_COLUMNS


class TestResolveScenario:
    def test_available_ids_are_sorted_and_match_the_registry(self) -> None:
        assert available_scenario_ids() == sorted(SCENARIO_REGISTRY.keys())

    def test_resolves_by_exact_id(self) -> None:
        assert resolve_scenario("sharp_crash").scenario_id == "sharp_crash"

    def test_resolves_by_alias_case_insensitively(self) -> None:
        assert resolve_scenario("CRASH").scenario_id == "sharp_crash"

    def test_unknown_name_raises_with_the_valid_list(self) -> None:
        with pytest.raises(ValidationError, match="Unknown scenario"):
            resolve_scenario("no_such_scenario")

    def test_blank_name_raises(self) -> None:
        with pytest.raises(ValidationError):
            resolve_scenario("   ")


def _synthetic_specs() -> list:
    return [spec for spec in SCENARIO_REGISTRY.values() if spec.source is None]


class TestSyntheticRegistryEntries:
    def test_every_synthetic_scenario_generates_bars_for_tickers_and_benchmark(self) -> None:
        for spec in _synthetic_specs():
            index = pd.bdate_range(start="2024-01-01", periods=spec.days)
            requested = (*spec.tickers, spec.benchmark)
            frames = spec.generator(
                PathRequest(index=index, tickers=requested, seed=spec.base_seed, params=spec.params)
            )
            assert set(frames) == set(requested)
            for frame in frames.values():
                assert len(frame) == spec.days
                assert list(frame.columns) == list(BAR_COLUMNS)

    def test_synthetic_path_count_default_is_two_hundred(self) -> None:
        for spec in _synthetic_specs():
            assert spec.path_count == 200


class TestRealRegistryEntries:
    def test_each_fixture_yields_a_replay_and_a_bootstrap_scenario(self) -> None:
        ids = set(SCENARIO_REGISTRY)
        assert "covid_crash_2020_replay" in ids
        assert "covid_crash_2020_bootstrap" in ids

    def test_real_scenarios_carry_a_fixture_source_and_the_unbound_generator(self) -> None:
        replay = SCENARIO_REGISTRY["covid_crash_2020_replay"]
        assert replay.source is not None
        assert replay.path_count == 1
        # The generator sentinel must not run without being bound by the seam.
        with pytest.raises(ValueError, match="not bound"):
            replay.generator(
                PathRequest(
                    index=pd.bdate_range("2024-01-01", periods=5),
                    tickers=replay.tickers,
                    seed=replay.base_seed,
                    params=replay.params,
                )
            )

    def test_default_scenarios_are_synthetic_only(self) -> None:
        from backtesting.domain.scenario_bench.registry import default_scenario_ids

        for scenario_id in default_scenario_ids():
            assert SCENARIO_REGISTRY[scenario_id].source is None
