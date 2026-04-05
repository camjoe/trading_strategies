from __future__ import annotations

import sqlite3

from trading.repositories.trades_repository import insert_trade


def add_manual_trade(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    ticker: str,
    side: str,
    qty: float,
    price: float,
    fee: float,
    trade_time: str,
) -> None:
    """Insert a manual trade record for the given account."""
    insert_trade(
        conn,
        account_id=account_id,
        ticker=ticker,
        side=side,
        qty=qty,
        price=price,
        fee=fee,
        trade_time=trade_time,
        note=None,
    )
