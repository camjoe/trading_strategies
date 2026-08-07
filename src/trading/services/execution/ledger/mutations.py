from __future__ import annotations

import sqlite3

from common.constants import SETTLEMENT_TICKER
from common.time import utc_now_iso
from trading.domain.accounting import _ensure_sufficient_cash_for_buy, _normalize_order_input
from trading.domain.exceptions import NotFoundError, ValidationError
from trading.persistence.unit_of_work import unit_of_work
from trading.repositories.books import BookRepository
from trading.repositories.ledger import LedgerRepository
from trading.repositories.orders import OrderRepository
from trading.repositories.positions import PositionRepository
from trading.services.accounts import get_account

# Manual entries are cash-flow ledger events or filled orders on the default
# book (the trades table was retired in revision 0006).
_LEDGER_REFERENCE_TYPE_MANUAL = "manual"


def _record_cash_event(
    conn: sqlite3.Connection,
    *,
    book_id: int,
    side: str,
    amount: float,
    entry_time: str,
) -> None:
    """Deposit (buy) or withdrawal (sell) of the settlement ticker."""
    book = BookRepository(conn).fetch_by_id(book_id=book_id)
    assert book is not None
    signed = amount if side == "buy" else -amount
    with unit_of_work(conn):
        LedgerRepository(conn).insert(
            book_id=book_id,
            entry_type="deposit" if side == "buy" else "withdrawal",
            amount=signed,
            reference_type=_LEDGER_REFERENCE_TYPE_MANUAL,
            reference_id=None,
            entry_time=entry_time,
            created_at=entry_time,
        )
        BookRepository(conn).update_balances(
            book_id=book_id,
            current_cash=book.current_cash + signed,
            current_equity=book.current_equity + signed,
            updated_at=entry_time,
        )


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
    """Record a manual trade against the account's default book.

    Since revision 0006 there is no account-level trades table: a settlement
    ticker (``CASH``) entry becomes a ledger deposit/withdrawal, and any other
    ticker becomes a filled order + fill applied to the default book (the same
    path runtime fills take). ``note`` is display-only and no longer
    persisted — the derived trade history carries the order linkage instead.
    """
    # The fill path imports submission (services.execution); import here keeps
    # module import order free of cycles.
    from trading.services.execution.submission import apply_book_fill

    del note
    account = get_account(conn, account_name)
    side, ticker = _normalize_order_input(side, ticker)
    book = BookRepository(conn).fetch_default_for_account(account_id=account.id)
    if book is None:
        raise NotFoundError(f"Default book missing for account '{account_name}'.")
    entry_time = trade_time or utc_now_iso()

    if ticker == SETTLEMENT_TICKER:
        _record_cash_event(
            conn,
            book_id=book.id,
            side=side,
            amount=float(qty) * float(price),
            entry_time=entry_time,
        )
        return

    if side == "buy":
        _ensure_sufficient_cash_for_buy(side, qty, price, fee, book.current_cash)
    else:
        position = PositionRepository(conn).fetch(book_id=book.id, symbol=ticker)
        held = position.qty if position is not None else 0.0
        if qty > held:
            raise ValidationError(f"Invalid sell for {ticker}: trying to sell {qty}, holding {held}.")

    order_repo = OrderRepository(conn)
    # One transaction for the whole manual fill: the order row, its fill, and the
    # book accounting are all-or-nothing.
    with unit_of_work(conn):
        order_id = order_repo.insert(
            book_id=book.id,
            account_id=account.id,
            symbol=ticker,
            side=side,
            qty=float(qty),
            requested_price=float(price),
            status="filled",
            filled_qty=float(qty),
            avg_fill_price=float(price),
            commission=float(fee),
            submitted_at=entry_time,
            updated_at=entry_time,
        )
        order_repo.insert_fill(
            order_id=order_id,
            filled_qty=float(qty),
            fill_price=float(price),
            fill_time=entry_time,
            commission=float(fee),
            exec_id=f"manual:{order_id}",
        )
        apply_book_fill(
            conn,
            book_id=book.id,
            order_id=order_id,
            side=side,
            symbol=ticker,
            fill_qty=float(qty),
            fill_price=float(price),
            transaction_cost=float(fee),
            fill_time=entry_time,
        )
