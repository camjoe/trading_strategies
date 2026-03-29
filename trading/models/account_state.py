from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AccountState:
    cash: float
    positions: dict[str, float]
    avg_cost: dict[str, float]
    realized_pnl: float
