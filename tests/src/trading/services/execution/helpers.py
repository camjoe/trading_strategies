"""Shared helpers for the execution service tests.

Co-located rather than in ``tests/support/`` because only this suite uses them
(see ``tests/support/README.md``).
"""

from __future__ import annotations

from typing import Any

from trading.repositories.snapshots import EquitySnapshotRepository


def insert_book_equity_snapshot(conn: Any, book_id: int, *, equity: float, snapshot_time: str) -> None:
    """Record a book equity snapshot with *equity* held entirely as cash.

    Gate and reconciliation tests read equity and ignore the composition, so the
    market-value and P&L columns stay zeroed.
    """
    EquitySnapshotRepository(conn).insert_for_book(
        book_id=book_id,
        snapshot_time=snapshot_time,
        cash=equity,
        market_value=0.0,
        equity=equity,
        realized_pnl=0.0,
        unrealized_pnl=0.0,
    )
