from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EvaluationDecisionScore:
    """Decision-ready view of a strategy evaluation.

    A keyless value object derived from ``StrategyEvaluationArtifact`` so that
    compare, promotion, and rotation can consume one comparable score/confidence
    contract instead of reading evaluation confidence fields directly. It carries
    no account/strategy identity so a caller can produce one per candidate
    (e.g. per rotation challenger).

    ``score`` mirrors the artifact's confidence-weighted blended score and is
    ``None`` when no evidence contributes; ``has_evidence`` makes that fallback
    explicit so consumers never treat a missing score as ``0``.
    """

    score: float | None = None
    confidence: float = 0.0
    backtest_confidence: float = 0.0
    paper_live_confidence: float = 0.0
    has_evidence: bool = False
    data_gaps: tuple[str, ...] = field(default_factory=tuple)
