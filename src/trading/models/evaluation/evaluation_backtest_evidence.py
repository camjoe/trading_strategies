from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EvaluationBacktestEvidence:
    available: bool = False
    run_id: int | None = None
    run_name: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    created_at: str | None = None
    trade_count: int | None = None
    snapshot_count: int | None = None
    starting_equity: float | None = None
    ending_equity: float | None = None
    total_return_pct: float | None = None
    max_drawdown_pct: float | None = None
    warnings: str | None = None
