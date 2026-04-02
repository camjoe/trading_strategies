"""Accounting service — trade recording and account-state loading."""
import sqlite3

from common.time import utc_now_iso
from trading.services.accounts_service import get_account
from trading.domain.accounting import (
    _ensure_sufficient_cash_for_buy,
    _normalize_order_input,
    compute_account_state,
)
from trading.repositories.trades_repository import fetch_trades_for_account, insert_trade


def load_trades(conn: sqlite3.Connection, account_id: int) -> list[sqlite3.Row]:
    return fetch_trades_for_account(conn, account_id=account_id)


def _account_state_from_db(conn: sqlite3.Connection, account_id: int, initial_cash: float):
    trades = load_trades(conn, account_id)
    return compute_account_state(initial_cash, trades)


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
    existing_state = _account_state_from_db(conn, account["id"], account["initial_cash"])
    _ensure_sufficient_cash_for_buy(side, qty, price, fee, existing_state.cash)
    insert_trade(
        conn,
        account_id=int(account["id"]),
        ticker=ticker,
        side=side,
        qty=float(qty),
        price=float(price),
        fee=float(fee),
        trade_time=trade_time or utc_now_iso(),
        note=note,
    )
