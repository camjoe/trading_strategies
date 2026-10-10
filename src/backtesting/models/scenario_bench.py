from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MetricDistribution:
    """One metric summarized across a scenario's Monte Carlo paths.

    ``count`` is the number of paths that produced a value: a metric a run could
    not compute (an undefined Sharpe on a flat path) is left out rather than read
    as zero, so the percentiles describe only real observations.
    """

    metric: str
    count: int
    mean: float | None
    p5: float | None
    p50: float | None
    p95: float | None
    minimum: float | None
    maximum: float | None

    def to_payload(self) -> dict[str, object]:
        return {
            "metric": self.metric,
            "count": self.count,
            "mean": self.mean,
            "p5": self.p5,
            "p50": self.p50,
            "p95": self.p95,
            "minimum": self.minimum,
            "maximum": self.maximum,
        }


@dataclass(frozen=True)
class ScenarioCellResult:
    """One strategy's outcome distribution in one scenario."""

    strategy: str
    scenario_id: str
    path_count: int
    distributions: dict[str, MetricDistribution]

    def to_payload(self) -> dict[str, object]:
        return {
            "strategy": self.strategy,
            "scenarioId": self.scenario_id,
            "pathCount": self.path_count,
            "distributions": {metric: dist.to_payload() for metric, dist in self.distributions.items()},
        }


@dataclass(frozen=True)
class BenchMatrix:
    """The full strategy-by-scenario grid of outcome distributions.

    ``strategies`` and ``scenario_ids`` fix the row and column order; ``cells`` is
    keyed by ``(strategy, scenario_id)``. Every strategy runs on the same paths per
    scenario, so a column compares strategies directly.
    """

    strategies: list[str]
    scenario_ids: list[str]
    cells: dict[tuple[str, str], ScenarioCellResult]

    def cell(self, strategy: str, scenario_id: str) -> ScenarioCellResult:
        return self.cells[(strategy, scenario_id)]

    def to_payload(self) -> dict[str, object]:
        return {
            "strategies": list(self.strategies),
            "scenarioIds": list(self.scenario_ids),
            "cells": [cell.to_payload() for cell in self.cells.values()],
        }
