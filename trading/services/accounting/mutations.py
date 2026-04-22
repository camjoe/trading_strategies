from __future__ import annotations

import sqlite3

from common.time import utc_now_iso
from trading.domain.accounting import _ensure_sufficient_cash_for_buy, _normalize_order_input
from trading.repositories.trades_repository import insert_trade
from trading.services.accounting.queries import load_account_state
from trading.services.accounts import get_account


def record_trade(
    conn: sqlite3.Connection,
    account_name: str,
    side: str,
    ticker: str,
    qty: float,
    price: float,
    fee: float,
    trade_time: str | None,
    note: str | None,
) -> None:
    account = get_account(conn, account_name)
    side, ticker = _normalize_order_input(side, ticker)
    existing_state = load_account_state(conn, account_id=account.id, initial_cash=account.initial_cash)
    _ensure_sufficient_cash_for_buy(side, qty, price, fee, existing_state.cash)
    insert_trade(
        conn,
        account_id=account.id,
        ticker=ticker,
        side=side,
        qty=float(qty),
        price=float(price),
        fee=float(fee),
        trade_time=trade_time or utc_now_iso(),
        note=note,
    )
