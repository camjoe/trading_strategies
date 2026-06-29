from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SleeveTradeState:
    cash: float
    positions: dict[str, float]
    avg_cost: dict[str, float]
    realized_pnl: float = 0.0
