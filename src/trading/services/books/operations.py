"""Book-attributed operational reads for interface consumers."""

from __future__ import annotations

import sqlite3
from typing import Any

from trading.domain.exceptions import NotFoundError
from trading.repositories.accounts import AccountRepository
from trading.repositories.books import BookRepository
from trading.repositories.daily_metrics import DailyMetricsRepository
from trading.repositories.positions import PositionRepository
from trading.repositories.risk import RiskDecisionRepository
from trading.repositories.snapshots import EquitySnapshotRepository


def fetch_book_operational_data(
    conn: sqlite3.Connection,
    *,
    account_name: str,
    limit: int = 100,
) -> dict[str, list[Any]]:
    """Return book-native positions, snapshots, metrics, and risk decisions."""
    account = AccountRepository(conn).fetch_by_name(account_name=account_name)
    if account is None:
        raise NotFoundError(f"Account not found: {account_name}")
    books = BookRepository(conn).fetch_for_account(account_id=account.id)
    book_names = {book.id: book.name for book in books}

    positions = [
        {
            "book_id": position.book_id,
            "book_name": book_names.get(position.book_id, f"book #{position.book_id}"),
            "ticker": position.symbol,
            "qty": position.qty,
            "avg_cost": position.avg_cost,
            "market_value": position.market_value,
            "unrealized_pnl": position.unrealized_pnl,
        }
        for position in PositionRepository(conn).fetch_for_account(account_id=account.id)
    ]
    snapshots = [
        {
            "book_id": book.id,
            "book_name": book.name,
            "snapshot": snapshot,
        }
        for book in books
        for snapshot in EquitySnapshotRepository(conn).fetch_history_for_book(book_id=book.id, limit=limit)
    ]
    metrics = [
        {
            "book_id": metric.book_id,
            "book_name": book_names.get(metric.book_id, f"book #{metric.book_id}"),
            "metric": metric,
        }
        for metric in DailyMetricsRepository(conn).fetch_book_rows_for_account(
            account_id=account.id,
            limit=limit,
        )
    ]
    risk_decisions = [
        {
            "book_id": decision.book_id,
            "book_name": (
                book_names.get(decision.book_id, f"book #{decision.book_id}") if decision.book_id is not None else None
            ),
            "decision": decision,
        }
        for decision in RiskDecisionRepository(conn).fetch_recent(account_id=account.id, limit=limit)
    ]
    return {
        "positions": positions,
        "snapshots": snapshots,
        "metrics": metrics,
        "risk_decisions": risk_decisions,
    }
