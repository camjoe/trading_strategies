from __future__ import annotations

import sqlite3

from trading.domain.accounting import compute_account_state
from trading.models import AccountState
from trading.repositories.trades import TradeRepository


def list_account_trades(conn: sqlite3.Connection, account_id: int) -> list[dict[str, object]]:
    return [dict(row) for row in TradeRepository(conn).fetch_for_account(account_id=account_id)]


def load_account_state(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    initial_cash: float | int | None,
) -> AccountState:
    trades = list_account_trades(conn, account_id)
    return compute_account_state(float(initial_cash or 0.0), trades)
