from __future__ import annotations

from dataclasses import dataclass

from trading.models.portfolio.account_exposure import AccountExposure


@dataclass(frozen=True, slots=True)
class PortfolioExposureRollup:
    """Cross-account exposure rollup payload contract.

    ``accounts`` holds one entry per account, ordered by account name.
    Totals sum only the accounts that have at least one equity snapshot
    (``accounts_with_snapshots`` of them), so missing data never reads as
    zero exposure.
    """

    accounts: tuple[AccountExposure, ...]
    accounts_with_snapshots: int
    total_cash: float
    total_market_value: float
    total_equity: float
