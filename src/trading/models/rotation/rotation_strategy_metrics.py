from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RotationStrategyMetrics:
    strategy_name: str
    trade_count: int
    risk_adjusted_return: float
    stability: float
    drawdown_penalty: float
    regime_fit: float
