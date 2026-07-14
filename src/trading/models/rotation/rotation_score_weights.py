from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RotationScoreWeights:
    risk_adjusted_return_weight: float = 1.0
    stability_weight: float = 0.25
    drawdown_penalty_weight: float = 0.20
    cost_penalty_weight: float = 0.10
    regime_fit_weight: float = 0.10
