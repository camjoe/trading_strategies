from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EvaluationWalkForwardEvidence:
    available: bool = False
    grouped: bool = False
    run_ids: list[int] = field(default_factory=list)
    average_return_pct: float | None = None
    median_return_pct: float | None = None
    best_return_pct: float | None = None
    worst_return_pct: float | None = None
