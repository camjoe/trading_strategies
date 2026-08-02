from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AccountInsert:
    """Repository-ready create payload after validation, defaults, and normalization."""

    name: str
    initial_cash: float
    created_at: str
    updated_at: str
    benchmark_ticker: str
    descriptive_name: str
