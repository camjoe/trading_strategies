from __future__ import annotations

from dataclasses import dataclass

from trading.models.portfolio.sector_concentration import SectorConcentration
from trading.models.portfolio.symbol_concentration import SymbolConcentration


@dataclass(frozen=True, slots=True)
class PortfolioConcentration:
    """Cross-account concentration payload.

    ``symbols`` and ``sectors`` are ordered by market value, largest first.
    Overlap is read from ``symbols`` entries with ``account_count`` > 1.
    Market values come from persisted ``positions`` rows (no live pricing).
    """

    symbols: tuple[SymbolConcentration, ...]
    sectors: tuple[SectorConcentration, ...]
    total_market_value: float
