from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SleeveStrategyScore:
    strategy_name: str
    param_set_id: int | None
    score: float
    score_components: dict[str, float]
    trade_count: int
    risk_adjusted_return: float
