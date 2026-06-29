from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EvaluationConfidence:
    backtest_confidence: float = 0.0
    paper_live_confidence: float = 0.0
    overall_confidence: float = 0.0
    blended_score: float | None = None
