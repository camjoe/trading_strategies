from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RotationStrategyScore:
    strategy_name: str
    score: float
    score_components: dict[str, float]
    trade_count: int
    risk_adjusted_return: float
