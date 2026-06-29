from __future__ import annotations

from dataclasses import dataclass, field

from trading.models.sleeves.constants import (
    DEFAULT_MAX_PORTFOLIO_GROSS_EXPOSURE,
    DEFAULT_MAX_SECTOR_CONCENTRATION_PCT,
    DEFAULT_MAX_SLEEVE_NOTIONAL_PCT,
    DEFAULT_MAX_SYMBOL_CONCENTRATION_PCT,
    DEFAULT_SYMBOL_SECTOR_MAP,
)


@dataclass(frozen=True, slots=True)
class SleeveRiskGateConfig:
    max_sleeve_notional_pct: float = DEFAULT_MAX_SLEEVE_NOTIONAL_PCT
    max_symbol_concentration_pct: float = DEFAULT_MAX_SYMBOL_CONCENTRATION_PCT
    max_portfolio_gross_exposure: float = DEFAULT_MAX_PORTFOLIO_GROSS_EXPOSURE
    max_sector_concentration_pct: float = DEFAULT_MAX_SECTOR_CONCENTRATION_PCT
    symbol_sector_map: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_SYMBOL_SECTOR_MAP))
