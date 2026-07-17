from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AccountInsert:
    """Repository-ready create payload after validation, defaults, and normalization."""

    name: str
    account_kind: str
    strategy: str
    initial_cash: float
    created_at: str
    benchmark_ticker: str
    descriptive_name: str
    goal_min_return_pct: float | None
    goal_max_return_pct: float | None
    goal_period: str
    trade_universes: str | None = None
