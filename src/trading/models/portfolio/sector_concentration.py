from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SectorConcentration:
    """One sector's share of total cross-account market value.

    ``portfolio_pct`` is 0-100; symbols missing from the sector reference
    data aggregate under ``UNCATEGORIZED_SECTOR``.
    """

    sector: str
    market_value: float
    portfolio_pct: float
    symbol_count: int
