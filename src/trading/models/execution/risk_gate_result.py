from __future__ import annotations

from dataclasses import dataclass

from trading.models.execution.book_trade_candidate import BookTradeCandidate
from trading.models.execution.risk_gate_decision import RiskGateDecision


@dataclass(frozen=True, slots=True)
class RiskGateResult:
    approved_intents: list[BookTradeCandidate]
    decisions: list[RiskGateDecision]
    allowed_count: int
    rescaled_count: int
    blocked_count: int
    gross_exposure_before: float
    gross_exposure_after: float
