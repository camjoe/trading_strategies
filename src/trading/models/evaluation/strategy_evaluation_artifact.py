from __future__ import annotations

from dataclasses import asdict, dataclass, field

from trading.models.evaluation.evaluation_backtest_evidence import EvaluationBacktestEvidence
from trading.models.evaluation.evaluation_basic_scope import EvaluationBasicScope
from trading.models.evaluation.evaluation_confidence import EvaluationConfidence
from trading.models.evaluation.evaluation_diagnostics import EvaluationDiagnostics
from trading.models.evaluation.evaluation_meta import EvaluationMeta
from trading.models.evaluation.evaluation_paper_live_evidence import EvaluationPaperLiveEvidence
from trading.models.evaluation.evaluation_walk_forward_evidence import EvaluationWalkForwardEvidence


@dataclass(frozen=True)
class StrategyEvaluationArtifact:
    meta: EvaluationMeta = field(default_factory=EvaluationMeta)
    basic: EvaluationBasicScope = field(default_factory=EvaluationBasicScope)
    backtest: EvaluationBacktestEvidence = field(default_factory=EvaluationBacktestEvidence)
    walk_forward: EvaluationWalkForwardEvidence = field(default_factory=EvaluationWalkForwardEvidence)
    paper_live: EvaluationPaperLiveEvidence = field(default_factory=EvaluationPaperLiveEvidence)
    confidence: EvaluationConfidence = field(default_factory=EvaluationConfidence)
    diagnostics: EvaluationDiagnostics = field(default_factory=EvaluationDiagnostics)

    def to_payload(self) -> dict[str, object]:
        return asdict(self)
