"""Book equity reconciliation — the pre-submit "our books vs reality" safety check.

Compares the account's rolled-up book equity against the latest equity snapshot and
returns kill-switch reasons (snapshot missing / stale / equity mismatch). This is the
*equity* reconciliation the pre-submit gate consumes; the *open-order* reconciliation
(reconcile_open_broker_orders) is a separate concern.

**Assumes books are NAV-marked first.** Book equity is fill-marked by the fill
path; the runtime marks books to market (`nav.mark_account_to_market`) before
the gate runs so both sides of this comparison are market-marked, matching the
market-marked snapshot. This function only reads.
"""

from __future__ import annotations

import sqlite3

from common.time import parse_utc_iso
from trading.repositories.books import BookRepository
from trading.repositories.snapshots import EquitySnapshotRepository
from trading.services.execution.constants import (
    KILL_SWITCH_REASON_RECONCILIATION_MISMATCH,
    KILL_SWITCH_REASON_RECONCILIATION_SNAPSHOT_MISSING,
    KILL_SWITCH_REASON_STALE_RECONCILIATION_SNAPSHOT,
    MAX_RECONCILIATION_SNAPSHOT_AGE_SECONDS,
    RECONCILIATION_EQUITY_TOLERANCE,
)


def is_snapshot_stale(*, now_iso: str, snapshot_time: str | None, max_age_seconds: int) -> bool:
    """Freshness math (not domain policy) for the reconciliation snapshot guard."""
    if snapshot_time is None:
        return True
    try:
        age_seconds = (parse_utc_iso(now_iso) - parse_utc_iso(snapshot_time)).total_seconds()
    except Exception:
        return True
    return age_seconds > float(max_age_seconds)


def reconcile_book_equity(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    now_iso: str,
    equity_tolerance: float = RECONCILIATION_EQUITY_TOLERANCE,
    max_snapshot_age_seconds: int = MAX_RECONCILIATION_SNAPSHOT_AGE_SECONDS,
) -> list[str]:
    """Return the reconciliation kill-switch reasons for the account (empty = clean)."""
    snapshot = EquitySnapshotRepository(conn).fetch_latest(account_id=account_id)
    if snapshot is None:
        return [KILL_SWITCH_REASON_RECONCILIATION_SNAPSHOT_MISSING]

    reasons: list[str] = []
    if is_snapshot_stale(
        now_iso=now_iso,
        snapshot_time=snapshot.snapshot_time,
        max_age_seconds=max_snapshot_age_seconds,
    ):
        reasons.append(KILL_SWITCH_REASON_STALE_RECONCILIATION_SNAPSHOT)

    books = BookRepository(conn).fetch_for_account(account_id=account_id)
    total_book_equity = sum(book.current_equity for book in books)
    if abs(total_book_equity - float(snapshot.equity)) > abs(float(equity_tolerance)):
        reasons.append(KILL_SWITCH_REASON_RECONCILIATION_MISMATCH)
    return reasons
