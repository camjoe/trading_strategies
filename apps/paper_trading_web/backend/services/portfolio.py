"""Portfolio rollup payload shaping for the UI backend.

Transport-only: aggregation lives in ``trading.services.analysis`` (P9);
this module reshapes those payloads into the camelCase response contract.
"""

from __future__ import annotations

import sqlite3

from trading.models.portfolio.account_exposure import AccountExposure
from trading.models.portfolio.portfolio_concentration import PortfolioConcentration
from trading.models.portfolio.portfolio_exposure_rollup import PortfolioExposureRollup
from trading.services.analysis import fetch_portfolio_concentration, fetch_portfolio_exposure


def _account_exposure_payload(exposure: AccountExposure) -> dict[str, object]:
    return {
        "accountId": exposure.account_id,
        "accountName": exposure.account_name,
        "snapshotTime": exposure.snapshot_time,
        "cash": exposure.cash,
        "marketValue": exposure.market_value,
        "equity": exposure.equity,
        "positionCount": exposure.position_count,
    }


def _exposure_payload(rollup: PortfolioExposureRollup) -> dict[str, object]:
    return {
        "accounts": [_account_exposure_payload(entry) for entry in rollup.accounts],
        "accountCount": len(rollup.accounts),
        "accountsWithSnapshots": rollup.accounts_with_snapshots,
        "totalCash": rollup.total_cash,
        "totalMarketValue": rollup.total_market_value,
        "totalEquity": rollup.total_equity,
    }


def _concentration_payload(concentration: PortfolioConcentration) -> dict[str, object]:
    return {
        "symbols": [
            {
                "symbol": entry.symbol,
                "sector": entry.sector,
                "marketValue": entry.market_value,
                "portfolioPct": entry.portfolio_pct,
                "accountCount": entry.account_count,
                "accountNames": list(entry.account_names),
            }
            for entry in concentration.symbols
        ],
        "sectors": [
            {
                "sector": entry.sector,
                "marketValue": entry.market_value,
                "portfolioPct": entry.portfolio_pct,
                "symbolCount": entry.symbol_count,
            }
            for entry in concentration.sectors
        ],
        "totalMarketValue": concentration.total_market_value,
    }


def build_portfolio_rollup_payload(conn: sqlite3.Connection) -> dict[str, object]:
    return {
        "exposure": _exposure_payload(fetch_portfolio_exposure(conn)),
        "concentration": _concentration_payload(fetch_portfolio_concentration(conn)),
    }
