"""Book NAV marking — mark a book's positions to market and refresh its equity.

Fills leave `books.current_equity` marked at *fill* price; the reconciliation
kill switch and the notional caps need equity marked at *current* prices, matching
the market-marked equity snapshot they reconcile against. This is the NAV marking
the runtime snapshot/reconciliation relies on: given the current price marks, it
re-marks each position and recomputes
`current_equity = current_cash + Σ(qty × mark)`.

Cash is untouched (marking never moves cash). Positions with no valid live mark are
held at cost basis (no unrealized P&L) and reported as unpriced.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping

from trading.models.execution.book_nav_mark_result import BookNavMarkResult
from trading.repositories.books import BookRepository
from trading.repositories.positions import PositionRepository
from trading.repositories.unit_of_work import unit_of_work


def mark_book_to_market(
    conn: sqlite3.Connection,
    *,
    book_id: int,
    prices: Mapping[str, float],
    as_of: str,
) -> BookNavMarkResult:
    """Re-mark one book's positions to ``prices`` and refresh its ``current_equity``."""
    book_repo = BookRepository(conn)
    position_repo = PositionRepository(conn)

    book = book_repo.fetch_by_id(book_id=book_id)
    if book is None:
        raise LookupError(f"Book {book_id} does not exist; cannot mark it to market.")

    market_value_total = 0.0
    unpriced_symbols: list[str] = []
    with unit_of_work(conn):
        for position in position_repo.fetch_for_book(book_id=book_id):
            price = prices.get(position.symbol)
            if price is not None and float(price) > 0:
                mark = float(price)
            else:
                # No live mark → hold at cost basis (zero unrealized), and flag it.
                mark = position.avg_cost
                unpriced_symbols.append(position.symbol)
            market_value = position.qty * mark
            position_repo.upsert(
                book_id=book_id,
                symbol=position.symbol,
                qty=position.qty,
                avg_cost=position.avg_cost,
                market_value=market_value,
                unrealized_pnl=market_value - position.qty * position.avg_cost,
                updated_at=as_of,
            )
            market_value_total += market_value

        current_equity = book.current_cash + market_value_total
        book_repo.update_balances(
            book_id=book_id,
            current_cash=book.current_cash,
            current_equity=current_equity,
            updated_at=as_of,
        )
    return BookNavMarkResult(
        book_id=book_id,
        current_cash=book.current_cash,
        current_equity=current_equity,
        unpriced_symbols=sorted(unpriced_symbols),
    )


def mark_account_to_market(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    prices: Mapping[str, float],
    as_of: str,
) -> list[BookNavMarkResult]:
    """Re-mark every book of an account to ``prices`` (default book + any additional books)."""
    books = BookRepository(conn).fetch_for_account(account_id=account_id)
    return [mark_book_to_market(conn, book_id=book.id, prices=prices, as_of=as_of) for book in books]
