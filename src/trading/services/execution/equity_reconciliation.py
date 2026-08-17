"""Book equity reconciliation — the pre-submit "our books vs reality" safety check.

Compares the account's rolled-up book equity against the latest equity snapshot and
returns kill-switch reasons (snapshot missing / equity mismatch). This is the
*equity* reconciliation the pre-submit gate consumes; the *open-order* reconciliation
(reconcile_open_broker_orders) is a separate concern.

Both sides are internally derived but by *different* write paths — book equity is
maintained by the fill path and re-marked by `nav.mark_account_to_market`, while the
snapshot is rolled up from `positions`. That is what makes the comparison worth
making: it catches those two aggregates drifting apart.

**There is deliberately no snapshot-age check.** Freshness is enforced by value, not
by a clock. The runtime marks books to market at *current* prices immediately before
this runs, while the snapshot holds *snapshot-time* prices, so for any account with
positions a meaningfully stale snapshot fails the equity tolerance on its own — a
cent of drift is far tighter than any duration worth picking. The only case an age
bound would have caught but the tolerance does not is an all-cash account, whose
equity is price-insensitive and whose old snapshot is therefore still correct (a
deposit or withdrawal moves the ledger and shows up as a mismatch). An age check
there would halt an accurate baseline for no safety gain.

**Assumes books are NAV-marked first**, per the above. This function only reads.
"""

from __future__ import annotations

import sqlite3

from trading.repositories.books import BookRepository
from trading.repositories.snapshots import EquitySnapshotRepository
from trading.services.execution.constants import (
    KILL_SWITCH_REASON_RECONCILIATION_MISMATCH,
    KILL_SWITCH_REASON_RECONCILIATION_SNAPSHOT_MISSING,
    RECONCILIATION_EQUITY_TOLERANCE,
)


def reconcile_book_equity(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    equity_tolerance: float = RECONCILIATION_EQUITY_TOLERANCE,
) -> list[str]:
    """Return the reconciliation kill-switch reasons for the account (empty = clean)."""
    snapshot = EquitySnapshotRepository(conn).fetch_latest(account_id=account_id)
    if snapshot is None:
        return [KILL_SWITCH_REASON_RECONCILIATION_SNAPSHOT_MISSING]

    reasons: list[str] = []
    books = BookRepository(conn).fetch_for_account(account_id=account_id)
    total_book_equity = sum(book.current_equity for book in books)
    if abs(total_book_equity - float(snapshot.equity)) > abs(float(equity_tolerance)):
        reasons.append(KILL_SWITCH_REASON_RECONCILIATION_MISMATCH)
    return reasons
