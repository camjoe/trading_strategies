"""Cross-account concentration rollup for analysis consumers (P9, D10).

Owns the symbol-level cross-account aggregation over persisted ``positions``
rows and the sector rollup over the operator-editable symbol->sector
reference data, beneath the stable ``trading.services.analysis`` package
surface.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping

from common.constants import SETTLEMENT_TICKER
from trading.domain.risk_gate import resolve_sector_for_symbol
from trading.models.portfolio.constants import UNCATEGORIZED_SECTOR
from trading.models.portfolio.portfolio_concentration import PortfolioConcentration
from trading.models.portfolio.sector_concentration import SectorConcentration
from trading.models.portfolio.symbol_concentration import SymbolConcentration
from trading.repositories.accounts import AccountRepository
from trading.repositories.positions import PositionRepository
from trading.services.books.sector_config import load_symbol_sector_map

# Fraction -> percent conversion for the portfolio_pct payload fields.
_PERCENT_SCALE = 100.0


def _portfolio_pct(market_value: float, total_market_value: float) -> float:
    if total_market_value == 0.0:
        return 0.0
    return (market_value / total_market_value) * _PERCENT_SCALE


def _symbol_entries(
    per_symbol_market_value: Mapping[str, float],
    per_symbol_accounts: Mapping[str, set[str]],
    sector_map: dict[str, str],
    total_market_value: float,
) -> tuple[SymbolConcentration, ...]:
    entries = [
        SymbolConcentration(
            symbol=symbol,
            sector=resolve_sector_for_symbol(symbol, symbol_sector_map=sector_map) or UNCATEGORIZED_SECTOR,
            market_value=market_value,
            portfolio_pct=_portfolio_pct(market_value, total_market_value),
            account_count=len(per_symbol_accounts[symbol]),
            account_names=tuple(sorted(per_symbol_accounts[symbol])),
        )
        for symbol, market_value in per_symbol_market_value.items()
    ]
    return tuple(sorted(entries, key=lambda e: (-e.market_value, e.symbol)))


def _sector_entries(
    symbols: tuple[SymbolConcentration, ...],
    total_market_value: float,
) -> tuple[SectorConcentration, ...]:
    per_sector_market_value: dict[str, float] = {}
    per_sector_symbol_count: dict[str, int] = {}
    for entry in symbols:
        per_sector_market_value[entry.sector] = per_sector_market_value.get(entry.sector, 0.0) + entry.market_value
        per_sector_symbol_count[entry.sector] = per_sector_symbol_count.get(entry.sector, 0) + 1
    entries = [
        SectorConcentration(
            sector=sector,
            market_value=market_value,
            portfolio_pct=_portfolio_pct(market_value, total_market_value),
            symbol_count=per_sector_symbol_count[sector],
        )
        for sector, market_value in per_sector_market_value.items()
    ]
    return tuple(sorted(entries, key=lambda e: (-e.market_value, e.sector)))


def fetch_portfolio_concentration(conn: sqlite3.Connection) -> PortfolioConcentration:
    """Aggregate cross-account symbol and sector concentration (D10).

    Market values come from persisted ``positions`` rows — no live pricing.
    The settlement ticker is excluded: it represents cash held as a position,
    not instrument exposure, and would misread as concentration risk.
    """
    positions = PositionRepository(conn)
    per_symbol_market_value: dict[str, float] = {}
    per_symbol_accounts: dict[str, set[str]] = {}

    for account in AccountRepository(conn).fetch_all():
        for position in positions.fetch_for_account(account_id=account.id):
            if position.symbol == SETTLEMENT_TICKER:
                continue
            per_symbol_market_value[position.symbol] = (
                per_symbol_market_value.get(position.symbol, 0.0) + position.market_value
            )
            per_symbol_accounts.setdefault(position.symbol, set()).add(account.name)

    total_market_value = sum(per_symbol_market_value.values())
    symbols = _symbol_entries(
        per_symbol_market_value,
        per_symbol_accounts,
        load_symbol_sector_map(),
        total_market_value,
    )
    return PortfolioConcentration(
        symbols=symbols,
        sectors=_sector_entries(symbols, total_market_value),
        total_market_value=total_market_value,
    )
