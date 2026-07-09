"""Operator-facing printed view of the cross-account concentration rollup.

Presentation only: the payload contract and aggregation live in
``trading.services.analysis.concentration``.
"""

from __future__ import annotations

import sqlite3

from trading.models.portfolio.portfolio_concentration import PortfolioConcentration
from trading.services.analysis.concentration import fetch_portfolio_concentration


def show_portfolio_concentration(conn: sqlite3.Connection) -> PortfolioConcentration:
    """Print the cross-account concentration rollup and return the payload."""
    concentration = fetch_portfolio_concentration(conn)

    if not concentration.symbols:
        print("No open positions found.")
        return concentration

    print("Portfolio concentration by symbol (cross-account, D10):")
    for entry in concentration.symbols:
        holders = ", ".join(entry.account_names)
        print(
            f"- {entry.symbol} | sector={entry.sector} | mv={entry.market_value:.2f} "
            f"| {entry.portfolio_pct:.2f}% | accounts={entry.account_count} ({holders})"
        )

    print("Sector rollup:")
    for sector_entry in concentration.sectors:
        print(
            f"- {sector_entry.sector} | mv={sector_entry.market_value:.2f} "
            f"| {sector_entry.portfolio_pct:.2f}% | symbols={sector_entry.symbol_count}"
        )

    overlap_count = sum(1 for entry in concentration.symbols if entry.account_count > 1)
    print(f"Total market value: {concentration.total_market_value:.2f}")
    print(f"Cross-account overlap: {overlap_count} symbol(s) held in more than one account")
    return concentration


__all__ = ["show_portfolio_concentration"]
