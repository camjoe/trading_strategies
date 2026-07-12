from __future__ import annotations

from dataclasses import dataclass, field

from trading.models.evaluation.backtest_freshness import BacktestFreshness


@dataclass(frozen=True)
class EvaluationDiagnostics:
    data_gaps: list[str] = field(default_factory=list)
    # Advisory backtest staleness (P12); None on artifacts built before P12.
    backtest_freshness: BacktestFreshness | None = None
