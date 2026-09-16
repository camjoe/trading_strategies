"""Aggregation must summarize present values and drop the missing ones."""

from __future__ import annotations

from backtesting.domain.scenario_bench.aggregation import BENCH_METRICS, metric_distribution, summarize_cell
from backtesting.models.backtest import BacktestResult


def _result(total_return: float, *, alpha: float | None, sharpe: float | None) -> BacktestResult:
    return BacktestResult(
        run_id=0,
        account_name="scenario_bench",
        start_date="2000-01-03",
        end_date="2000-06-01",
        tickers=["SYN1"],
        trade_count=2,
        ending_equity=100.0,
        total_return_pct=total_return,
        benchmark_return_pct=2.0,
        alpha_pct=alpha,
        max_drawdown_pct=-5.0,
        warnings=[],
        sharpe_ratio=sharpe,
    )


class TestMetricDistribution:
    def test_summarizes_present_values(self) -> None:
        dist = metric_distribution("total_return_pct", [0.0, 10.0, 20.0])
        assert dist.count == 3
        assert dist.p50 == 10.0
        assert dist.minimum == 0.0
        assert dist.maximum == 20.0
        assert dist.mean == 10.0

    def test_drops_missing_values_rather_than_counting_zero(self) -> None:
        dist = metric_distribution("sharpe_ratio", [None, 2.0, None, 4.0])
        assert dist.count == 2
        assert dist.mean == 3.0

    def test_all_missing_yields_empty_distribution(self) -> None:
        dist = metric_distribution("sharpe_ratio", [None, None])
        assert dist.count == 0
        assert dist.p50 is None
        assert dist.mean is None


class TestSummarizeCell:
    def test_builds_one_distribution_per_bench_metric(self) -> None:
        results = [
            _result(10.0, alpha=8.0, sharpe=1.0),
            _result(20.0, alpha=None, sharpe=2.0),
        ]
        cell = summarize_cell("trend", "sharp_crash", results)
        assert cell.strategy == "trend"
        assert cell.scenario_id == "sharp_crash"
        assert cell.path_count == 2
        assert set(cell.distributions) == set(BENCH_METRICS)
        assert cell.distributions["total_return_pct"].p50 == 15.0
        # One alpha was missing, so only one observation is counted.
        assert cell.distributions["alpha_pct"].count == 1
