from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from trading.repositories.sleeves import SleeveRepository
from trading.repositories.snapshots import EquitySnapshotRepository

DEFAULT_EQUITY_TOLERANCE = 0.01


@dataclass(frozen=True, slots=True)
class SleeveEquityReconciliationResult:
    account_id: int
    account_equity: float
    total_sleeve_equity: float
    equity_difference: float
    tolerance: float
    within_tolerance: bool
    snapshot_time: str | None


def reconcile_sleeves_vs_account_equity(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    account_equity: float,
    tolerance: float = DEFAULT_EQUITY_TOLERANCE,
    snapshot_time: str | None = None,
) -> SleeveEquityReconciliationResult:
    sleeves = SleeveRepository(conn).fetch_for_account(account_id=int(account_id))
    total_sleeve_equity = sum(s.current_equity for s in sleeves)
    difference = total_sleeve_equity - float(account_equity)
    abs_tolerance = abs(float(tolerance))
    return SleeveEquityReconciliationResult(
        account_id=int(account_id),
        account_equity=float(account_equity),
        total_sleeve_equity=total_sleeve_equity,
        equity_difference=difference,
        tolerance=abs_tolerance,
        within_tolerance=abs(difference) <= abs_tolerance,
        snapshot_time=snapshot_time,
    )


def reconcile_sleeves_vs_latest_snapshot(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    tolerance: float = DEFAULT_EQUITY_TOLERANCE,
) -> SleeveEquityReconciliationResult:
    latest_snapshot = EquitySnapshotRepository(conn).fetch_latest(account_id=int(account_id))
    if latest_snapshot is None:
        raise ValueError(f"No equity snapshot available for account_id={account_id}.")
    return reconcile_sleeves_vs_account_equity(
        conn,
        account_id=int(account_id),
        account_equity=latest_snapshot.equity,
        tolerance=tolerance,
        snapshot_time=latest_snapshot.snapshot_time,
    )
