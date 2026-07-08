from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RotationStrategyMetrics:
    strategy_name: str
    param_set_id: int | None
    trade_count: int
    risk_adjusted_return: float
    stability: float
    drawdown_penalty: float
    cost_penalty: float
    regime_fit: float
