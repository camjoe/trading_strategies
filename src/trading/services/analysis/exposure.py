"""Cross-account exposure rollup for analysis consumers (P9 v1).

Owns the read-only aggregation over equity snapshots and open positions
beneath the stable ``trading.services.analysis`` package surface.
"""

from __future__ import annotations

import sqlite3

from trading.models.portfolio.account_exposure import AccountExposure
from trading.models.portfolio.portfolio_exposure_rollup import PortfolioExposureRollup
from trading.repositories.accounts import AccountRepository
from trading.repositories.positions import PositionRepository
from trading.repositories.snapshots import EquitySnapshotRepository


def _account_exposure(
    account_id: int,
    account_name: str,
    snapshots: EquitySnapshotRepository,
    positions: PositionRepository,
) -> AccountExposure:
    latest = snapshots.fetch_latest(account_id=account_id)
    position_count = len(positions.fetch_for_account(account_id=account_id))
    if latest is None:
        return AccountExposure(
            account_id=account_id,
            account_name=account_name,
            snapshot_time=None,
            cash=None,
            market_value=None,
            equity=None,
            position_count=position_count,
        )
    return AccountExposure(
        account_id=account_id,
        account_name=account_name,
        snapshot_time=latest.snapshot_time,
        cash=latest.cash,
        market_value=latest.market_value,
        equity=latest.equity,
        position_count=position_count,
    )


def fetch_portfolio_exposure(conn: sqlite3.Connection) -> PortfolioExposureRollup:
    """Aggregate latest-snapshot exposure across all accounts.

    Accounts without any equity snapshot appear in the payload with None
    balances and are excluded from the totals, so a not-yet-snapshotted
    account never reads as zero exposure.
    """
    snapshots = EquitySnapshotRepository(conn)
    positions = PositionRepository(conn)
    exposures = tuple(
        _account_exposure(account.id, account.name, snapshots, positions)
        for account in AccountRepository(conn).fetch_all()
    )
    covered = [e for e in exposures if e.snapshot_time is not None]
    return PortfolioExposureRollup(
        accounts=exposures,
        accounts_with_snapshots=len(covered),
        total_cash=sum(e.cash or 0.0 for e in covered),
        total_market_value=sum(e.market_value or 0.0 for e in covered),
        total_equity=sum(e.equity or 0.0 for e in covered),
    )
