"""Test helper: resolve a strategy label to a strategies-row id (P3 clean schema).

Backtest tables key the strategy as a ``strategy_id`` FK. Tests that raw-insert
backtest runs use this to obtain a valid id, draft-creating a catalog row when
the strategy catalog has not been seeded in the fixture.
"""

from __future__ import annotations

import sqlite3

from common.time import utc_now_iso
from trading.repositories.book_bridge import strategy_id_for_label


def strategy_id_for(conn: sqlite3.Connection, label: str, *, now_iso: str | None = None) -> int:
    strategy_id = strategy_id_for_label(conn, label, now_iso=now_iso or utc_now_iso())
    assert strategy_id is not None  # non-empty label always resolves or draft-creates
    return strategy_id
