from __future__ import annotations

import sqlite3

from common.constants import SETTLEMENT_TICKER
from trading.domain.accounting.account import compute_account_state
from trading.models import AccountState
from trading.repositories.ledger import LedgerRepository
from trading.repositories.orders import OrderRepository


def _fill_events(conn: sqlite3.Connection, account_id: int) -> list[dict[str, object]]:
    return [
        {
            "book_id": event.book_id,
            "ticker": event.ticker,
            "side": event.side,
            "qty": event.qty,
            "price": event.price,
            "fee": event.fee,
            "trade_time": event.trade_time,
            "note": f"order={event.order_id}",
        }
        for event in OrderRepository(conn).fetch_fill_events_for_account(account_id=account_id)
    ]


def _cash_events(conn: sqlite3.Connection, account_id: int) -> list[dict[str, object]]:
    # Ledger deposits/withdrawals map onto the settlement-ticker trade shape
    # the replay already understands: a deposit is a CASH buy (inflow), a
    # withdrawal a CASH sell (outflow). Ledger amounts are signed cash flows.
    events: list[dict[str, object]] = []
    for entry in LedgerRepository(conn).fetch_cash_events_for_account(account_id=account_id):
        amount = float(entry.amount)
        events.append(
            {
                "book_id": entry.book_id,
                "ticker": SETTLEMENT_TICKER,
                "side": "buy" if entry.entry_type == "deposit" else "sell",
                "qty": abs(amount),
                "price": 1.0,
                "fee": 0.0,
                "trade_time": entry.entry_time,
                "note": entry.entry_type,
            }
        )
    return events


def list_account_trades(conn: sqlite3.Connection, account_id: int) -> list[dict[str, object]]:
    """Account trade history derived from order fills plus ledger cash events.

    The ``trades`` table was retired (revision 0006): ``orders``/``order_fills``
    are the only execution history, and deposits/withdrawals live in the
    ``ledger``. Rows keep the retired table's key shape (``ticker``, ``side``,
    ``qty``, ``price``, ``fee``, ``trade_time``, ``note``) so replay math and
    display payloads are unchanged.
    """
    events = _fill_events(conn, account_id) + _cash_events(conn, account_id)
    events.sort(key=lambda event: str(event["trade_time"]))
    return events


def load_account_state(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    initial_cash: float | int | None,
) -> AccountState:
    trades = list_account_trades(conn, account_id)
    return compute_account_state(float(initial_cash or 0.0), trades)
