from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AccountState:
    cash: float
    positions: dict[str, float]
    avg_cost: dict[str, float]
    realized_pnl: float
    total_deposited: float = field(default=0.0)
