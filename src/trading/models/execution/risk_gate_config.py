from __future__ import annotations

from dataclasses import dataclass, field

from trading.models.execution.risk_gate_constants import (
    DEFAULT_MAX_BOOK_NOTIONAL_PCT,
    DEFAULT_MAX_PORTFOLIO_GROSS_EXPOSURE,
    DEFAULT_MAX_SECTOR_CONCENTRATION_PCT,
    DEFAULT_MAX_SYMBOL_CONCENTRATION_PCT,
)


@dataclass(frozen=True, slots=True)
class RiskGateConfig:
    max_book_notional_pct: float = DEFAULT_MAX_BOOK_NOTIONAL_PCT
    max_symbol_concentration_pct: float = DEFAULT_MAX_SYMBOL_CONCENTRATION_PCT
    max_portfolio_gross_exposure: float = DEFAULT_MAX_PORTFOLIO_GROSS_EXPOSURE
    max_sector_concentration_pct: float = DEFAULT_MAX_SECTOR_CONCENTRATION_PCT
    # Symbol→sector reference data is operator config; the service layer loads it
    # from src/infrastructure/config/symbol_sectors.json and injects it here.
    # An empty map means no sector-concentration limits are applied.
    symbol_sector_map: dict[str, str] = field(default_factory=dict)
