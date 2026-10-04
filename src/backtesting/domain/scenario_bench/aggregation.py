"""Reduce a scenario's per-path runs into an outcome distribution per metric.

Pure. Given the ``BacktestResult`` list for one strategy over one scenario's
paths, it produces one :class:`MetricDistribution` per bench metric. A metric a
run left ``None`` is dropped, never counted as zero.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from backtesting.models.backtest import BacktestResult
from backtesting.models.scenario_bench import MetricDistribution, ScenarioCellResult

# The result fields the bench summarizes. Return and drawdown are the headline
# outcome; alpha places them against the scenario benchmark; Sharpe carries the
# risk-adjusted view. All are attributes of BacktestResult.
BENCH_METRICS = ("total_return_pct", "max_drawdown_pct", "sharpe_ratio", "alpha_pct")

# Percentile band reported for each metric.
_LOW_PERCENTILE = 5.0
_MID_PERCENTILE = 50.0
_HIGH_PERCENTILE = 95.0


def metric_distribution(metric: str, values: Sequence[float | None]) -> MetricDistribution:
    """Summarize one metric's values across paths, dropping the missing ones."""
    present = [float(value) for value in values if value is not None]
    if not present:
        return MetricDistribution(
            metric=metric, count=0, mean=None, p5=None, p50=None, p95=None, minimum=None, maximum=None
        )
    array = np.array(present, dtype=float)
    return MetricDistribution(
        metric=metric,
        count=len(present),
        mean=float(array.mean()),
        p5=float(np.percentile(array, _LOW_PERCENTILE)),
        p50=float(np.percentile(array, _MID_PERCENTILE)),
        p95=float(np.percentile(array, _HIGH_PERCENTILE)),
        minimum=float(array.min()),
        maximum=float(array.max()),
    )


def summarize_cell(
    strategy: str,
    scenario_id: str,
    results: Sequence[BacktestResult],
) -> ScenarioCellResult:
    """Build the outcome distributions for one strategy over one scenario's paths."""
    distributions = {
        metric: metric_distribution(metric, [getattr(result, metric) for result in results])
        for metric in BENCH_METRICS
    }
    return ScenarioCellResult(
        strategy=strategy,
        scenario_id=scenario_id,
        path_count=len(results),
        distributions=distributions,
    )
