"""End to end: run_bench simulates real paths and persists nothing."""

from __future__ import annotations

import sqlite3

import numpy as np
import pandas as pd

import backtesting.services.scenario_fixtures as scenario_fixtures
from backtesting.composition import run_bench
from backtesting.domain.scenario_bench.contracts import (
    SCENARIO_MODE_BOOTSTRAP,
    SCENARIO_MODE_REPLAY,
    FixtureSource,
    ScenarioSpec,
)
from backtesting.domain.scenario_bench.generators import unbound_generator
from backtesting.domain.scenario_bench.registry import resolve_scenario
from trading.models.market_data import BAR_CLOSE, BAR_COLUMNS, BAR_HIGH, BAR_LOW, BAR_OPEN, BAR_VOLUME
from trading.services.accounts.mutations import get_account


def _fixture_bars(seed: int, periods: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    index = pd.bdate_range("2020-01-02", periods=periods)
    close = 100.0 * np.cumprod(1.0 + rng.normal(0.0003, 0.02, periods))
    open_ = np.concatenate([[close[0]], close[:-1]])
    frame = pd.DataFrame(
        {
            BAR_OPEN: open_,
            BAR_HIGH: np.maximum(open_, close) * 1.01,
            BAR_LOW: np.minimum(open_, close) * 0.99,
            BAR_CLOSE: close,
            BAR_VOLUME: np.full(periods, 2_000_000.0),
        },
        index=index,
    )
    return frame[list(BAR_COLUMNS)]


def _write_fixture(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(scenario_fixtures, "SCENARIO_BENCH_FIXTURES_DIR", tmp_path)
    frames = {"RT1": _fixture_bars(1, 60), "RT2": _fixture_bars(2, 60), "RB": _fixture_bars(3, 60)}
    scenario_fixtures.save_fixture("test_episode", frames)


def _real_spec(scenario_id: str, mode: str, *, path_count: int, days: int) -> ScenarioSpec:
    return ScenarioSpec(
        scenario_id=scenario_id,
        generator=unbound_generator,
        params={},
        path_count=path_count,
        tickers=("RT1", "RT2"),
        benchmark="RB",
        base_seed=9000,
        days=days,
        source=FixtureSource(fixture_id="test_episode", mode=mode),
    )


class TestRunBench:
    def test_produces_a_distribution_per_cell(self, conn: sqlite3.Connection) -> None:
        scenario = resolve_scenario("strong_uptrend")
        matrix = run_bench(
            conn,
            strategy_names=["trend"],
            scenario_specs=[scenario],
            paths_override=3,
            slippage_bps=5.0,
            fee_per_trade=0.0,
        )

        cell = matrix.cell("trend", "strong_uptrend")
        assert cell.path_count == 3
        distribution = cell.distributions["total_return_pct"]
        assert distribution.count == 3
        assert distribution.p50 is not None

    def test_persists_no_backtest_runs(self, conn: sqlite3.Connection) -> None:
        scenario = resolve_scenario("choppy_flat")
        run_bench(
            conn,
            strategy_names=["trend", "mean_reversion"],
            scenario_specs=[scenario],
            paths_override=2,
            slippage_bps=5.0,
            fee_per_trade=0.0,
        )

        # The bench is behavioral, not evidence: it must not pollute the run corpus.
        run_count = int(conn.execute("SELECT COUNT(*) AS n FROM backtest_runs").fetchone()["n"])
        assert run_count == 0


class TestRunBenchRealData:
    def test_replay_runs_one_deterministic_path_and_updates_the_benchmark(
        self, conn: sqlite3.Connection, tmp_path, monkeypatch
    ) -> None:
        _write_fixture(tmp_path, monkeypatch)
        spec = _real_spec("test_episode_replay", SCENARIO_MODE_REPLAY, path_count=1, days=252)

        matrix = run_bench(
            conn,
            strategy_names=["trend"],
            scenario_specs=[spec],
            paths_override=None,
            slippage_bps=5.0,
            fee_per_trade=0.0,
        )

        cell = matrix.cell("trend", "test_episode_replay")
        assert cell.path_count == 1
        assert cell.distributions["total_return_pct"].count == 1
        # The reserved account was pointed at the real benchmark of this run.
        assert get_account(conn, "scenario_bench").benchmark_ticker == "RB"

    def test_bootstrap_runs_many_paths_and_persists_nothing(
        self, conn: sqlite3.Connection, tmp_path, monkeypatch
    ) -> None:
        _write_fixture(tmp_path, monkeypatch)
        spec = _real_spec("test_episode_bootstrap", SCENARIO_MODE_BOOTSTRAP, path_count=200, days=40)

        matrix = run_bench(
            conn,
            strategy_names=["trend", "mean_reversion"],
            scenario_specs=[spec],
            paths_override=3,
            slippage_bps=5.0,
            fee_per_trade=0.0,
        )

        assert matrix.cell("trend", "test_episode_bootstrap").distributions["total_return_pct"].count == 3
        run_count = int(conn.execute("SELECT COUNT(*) AS n FROM backtest_runs").fetchone()["n"])
        assert run_count == 0
