from __future__ import annotations

from dataclasses import dataclass, field

from trading.models.evaluation.backtest_freshness import BacktestFreshness


@dataclass(frozen=True)
class EvaluationDiagnostics:
    data_gaps: list[str] = field(default_factory=list)
    # Advisory backtest staleness; None on artifacts built before the freshness diagnostic existed.
    backtest_freshness: BacktestFreshness | None = None
