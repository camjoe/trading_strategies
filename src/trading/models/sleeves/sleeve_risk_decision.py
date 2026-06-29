from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SleeveRiskDecision:
    sleeve_id: int
    symbol: str
    side: str
    action: str
    reason_code: str
    requested_qty: int
    approved_qty: int
    requested_notional: float
    approved_notional: float
