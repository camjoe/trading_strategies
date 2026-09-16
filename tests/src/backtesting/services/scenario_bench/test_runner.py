"""The runner must generate each path once, share it across strategies, and grid."""

from __future__ import annotations

import pandas as pd

from backtesting.domain.scenario_bench.contracts import PathRequest, ScenarioSpec
from backtesting.models.backtest import BacktestConfig, BacktestResult
from backtesting.services.scenario_bench import (
    BenchRunContext,
    render_bench_matrix,
    run_scenario_bench,
)

_CONTEXT = BenchRunContext(
    account_name="scenario_bench",
    tickers_file="unused.txt",
    slippage_bps=0.0,
    fee_per_trade=0.0,
)

# Fixed per-strategy return, so a cell's median equals the strategy's value and a
# misplaced cell is visible.
_STRATEGY_RETURN = {"trend": 12.0, "mean_reversion": -3.0}


def _fake_run_path(cfg: BacktestConfig, frames: dict[str, pd.DataFrame]) -> BacktestResult:
    total_return = _STRATEGY_RETURN[cfg.strategy or ""]
    return BacktestResult(
        run_id=0,
        account_name=cfg.account_name,
        start_date=cfg.start or "",
        end_date=cfg.end or "",
        tickers=["SYN1"],
        trade_count=1,
        ending_equity=100.0,
        total_return_pct=total_return,
        benchmark_return_pct=2.0,
        alpha_pct=total_return - 2.0,
        max_drawdown_pct=-4.0,
        warnings=[],
        sharpe_ratio=1.0,
    )


def _counting_spec(scenario_id: str, seed: int, calls: list[int]) -> ScenarioSpec:
    def generator(request: PathRequest) -> dict[str, pd.DataFrame]:
        calls.append(request.seed)
        return {ticker: pd.DataFrame(index=request.index) for ticker in request.tickers}

    return ScenarioSpec(
        scenario_id=scenario_id,
        generator=generator,
        params={},
        path_count=3,
        tickers=("SYN1",),
        benchmark="BENCH",
        base_seed=seed,
        days=10,
    )


class TestRunScenarioBench:
    def test_grids_strategies_by_scenarios_with_per_cell_distributions(self) -> None:
        calls: list[int] = []
        scenarios = [_counting_spec("crash", 100, calls), _counting_spec("bull", 200, calls)]
        matrix = run_scenario_bench(
            strategies=["trend", "mean_reversion"],
            scenarios=scenarios,
            context=_CONTEXT,
            run_path=_fake_run_path,
        )

        assert matrix.strategies == ["trend", "mean_reversion"]
        assert matrix.scenario_ids == ["crash", "bull"]
        crash_trend = matrix.cell("trend", "crash")
        assert crash_trend.path_count == 3
        assert crash_trend.distributions["total_return_pct"].p50 == 12.0
        assert matrix.cell("mean_reversion", "bull").distributions["total_return_pct"].p50 == -3.0

    def test_generates_each_path_once_and_shares_it_across_strategies(self) -> None:
        calls: list[int] = []
        scenarios = [_counting_spec("crash", 100, calls)]
        run_scenario_bench(
            strategies=["trend", "mean_reversion"],
            scenarios=scenarios,
            context=_CONTEXT,
            run_path=_fake_run_path,
        )
        # Three paths, generated once each — not once per strategy.
        assert calls == [100, 101, 102]

    def test_paths_override_replaces_the_catalog_count(self) -> None:
        calls: list[int] = []
        scenarios = [_counting_spec("crash", 100, calls)]
        matrix = run_scenario_bench(
            strategies=["trend"],
            scenarios=scenarios,
            context=_CONTEXT,
            run_path=_fake_run_path,
            paths_override=2,
        )
        assert calls == [100, 101]
        assert matrix.cell("trend", "crash").path_count == 2


class TestRenderBenchMatrix:
    def test_renders_a_row_per_strategy_and_names_the_metric(self) -> None:
        calls: list[int] = []
        matrix = run_scenario_bench(
            strategies=["trend", "mean_reversion"],
            scenarios=[_counting_spec("crash", 100, calls)],
            context=_CONTEXT,
            run_path=_fake_run_path,
        )
        text = render_bench_matrix(matrix)
        assert "total_return_pct" in text
        assert "trend" in text
        assert "crash" in text
