"""Operator-facing equity snapshot commands.

``snapshot_account`` captures a persisted equity snapshot (the sole write in the
reporting package) and echoes the account report; ``show_snapshots`` prints the
recent snapshot history. Report rendering is delegated to ``account``.
"""

from __future__ import annotations

import sqlite3

from common.time import utc_now_iso
from trading.repositories.snapshots import EquitySnapshotRepository
from trading.services.accounts import get_account, list_account_snapshots
from trading.services.market_data import MarketDataProvider
from trading.services.reporting.account import account_report


def snapshot_account(
    conn: sqlite3.Connection,
    account_name: str,
    snapshot_time: str | None,
    *,
    provider: MarketDataProvider | None = None,
) -> None:
    account = get_account(conn, account_name)
    stats, _ = account_report(conn, account_name, provider=provider)
    EquitySnapshotRepository(conn).insert(
        account_id=account.id,
        snapshot_time=snapshot_time or utc_now_iso(),
        cash=stats["cash"],
        market_value=stats["market_value"],
        equity=stats["equity"],
        realized_pnl=stats["realized_pnl"],
        unrealized_pnl=stats["unrealized_pnl"],
    )
    print("Snapshot saved.")


def show_snapshots(conn: sqlite3.Connection, account_name: str, limit: int) -> None:
    account = get_account(conn, account_name)
    rows = list_account_snapshots(conn, account.id, limit=int(limit))

    if not rows:
        print("No snapshots found.")
        return

    print(f"Snapshot history (latest {limit}) for {account_name}:")
    for row in rows:
        print(
            f"- {row.snapshot_time} | equity={row.equity:.2f} cash={row.cash:.2f} "
            f"mv={row.market_value:.2f} realized={row.realized_pnl:.2f} "
            f"unrealized={row.unrealized_pnl:.2f}"
        )


__all__ = ["show_snapshots", "snapshot_account"]
