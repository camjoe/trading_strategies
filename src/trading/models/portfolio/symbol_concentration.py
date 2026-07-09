from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SymbolConcentration:
    """One symbol's cross-account concentration entry (D10).

    ``portfolio_pct`` is the symbol's share of total cross-account market
    value, 0-100. ``account_count`` > 1 means the symbol is held in multiple
    accounts (cross-account overlap). ``sector`` falls back to
    ``UNCATEGORIZED_SECTOR`` for symbols missing from the reference data.
    """

    symbol: str
    sector: str
    market_value: float
    portfolio_pct: float
    account_count: int
    account_names: tuple[str, ...]
