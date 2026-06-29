from __future__ import annotations

from dataclasses import dataclass

from trading.models.sleeves.sleeve_risk_decision import SleeveRiskDecision
from trading.models.sleeves.sleeve_trade_intent import SleeveTradeIntent


@dataclass(frozen=True, slots=True)
class SleeveRiskGateResult:
    approved_intents: list[SleeveTradeIntent]
    decisions: list[SleeveRiskDecision]
    allowed_count: int
    rescaled_count: int
    blocked_count: int
    gross_exposure_before: float
    gross_exposure_after: float
