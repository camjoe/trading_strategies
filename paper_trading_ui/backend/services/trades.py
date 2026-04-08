"""Backend service helper for manual trade injection in the paper-trading UI.

Provides ``add_manual_trade``, a thin wrapper around
``trading.services.accounting_service.record_trade`` that keeps route modules
decoupled from the canonical accounting service import path.
"""
from __future__ import annotations

import sqlite3

from trading.services.accounting_service import record_trade


def add_manual_trade(
    conn: sqlite3.Connection,
    *,
    account_name: str,
    ticker: str,
    side: str,
    qty: float,
    price: float,
    fee: float,
    trade_time: str,
) -> None:
    """Insert a manual trade record for the given account via the accounting service."""
    record_trade(
        conn,
        account_name=account_name,
        side=side,
        ticker=ticker,
        qty=qty,
        price=price,
        fee=fee,
        trade_time=trade_time,
        note=None,
    )
