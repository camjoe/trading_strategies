from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EvaluationWalkForwardEvidence:
    """Out-of-sample window record from a walk-forward optimization experiment.

    ``window_returns`` carries each window's OOS return in chronological order —
    the full distribution, not just its summary statistics — so consumers can
    measure dispersion directly instead of inferring it from the range.
    """

    available: bool = False
    window_returns: list[float] = field(default_factory=list)
    average_return_pct: float | None = None
    median_return_pct: float | None = None
    best_return_pct: float | None = None
    worst_return_pct: float | None = None
