"""End to end: run_bench simulates real paths and persists nothing."""

from __future__ import annotations

import sqlite3

from backtesting.composition import run_bench
from backtesting.domain.scenario_bench.registry import resolve_scenario


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
