"""Queries for autonomy monitoring data.

Uses repository layer functions for all data access. Covers every account the
system runs autonomously (all accounts — there is no other kind).
"""

from __future__ import annotations

import sqlite3
from typing import Any

from trading.domain.exceptions import NotFoundError
from trading.domain.metrics.portfolio_math import strategy_return_pct
from trading.models import AccountRecord
from trading.models.books import BookAssignmentView, BookRecord
from trading.repositories.accounts import AccountRepository
from trading.repositories.books import BookRepository
from trading.repositories.daily_metrics import DailyMetricsRepository
from trading.repositories.risk import RiskDecisionRepository
from trading.repositories.rotation_decisions import RotationDecisionRepository
from trading.services.books.book_assignments import list_report_books

# The account's non-default books paired with their open assignment, fetched once
# per request and shared by the overview, book, and rotation builders.
ReportBooks = list[tuple[BookRecord, BookAssignmentView | None]]


def _return_pct(equity: float, basis: float) -> float:
    """Percent return of ``equity`` against a capital ``basis``.

    Rounds to 2 dp and returns ``0.0`` when there is no basis to measure
    against, so callers never divide by zero. Reuses the shared portfolio
    math so account/book returns stay defined the same way everywhere.
    """
    return round(strategy_return_pct(equity, basis), 2) if basis else 0.0


def _build_account_overview(
    conn: sqlite3.Connection,
    account: AccountRecord,
    report_books: ReportBooks,
) -> dict[str, Any]:
    """The account's headline balances, measured against ``initial_cash``.

    Account totals are the Σ over *every* book, default included: the default
    book holds whatever capital was not carved out into sleeves, so summing
    only the reported (non-default) books would compare a partial equity
    against the whole account's capital and report a fictitious return.
    """
    account_books = BookRepository(conn).fetch_for_account(account_id=account.id)
    total_equity = sum(b.current_equity for b in account_books)
    total_cash = sum(b.current_cash for b in account_books)

    return {
        "account_id": account.id,
        "name": account.name,
        "initial_cash": account.initial_cash,
        "total_equity": round(total_equity, 2),
        "total_cash": round(total_cash, 2),
        "positions_market_value": round(total_equity - total_cash, 2),
        "return_pct": _return_pct(total_equity, account.initial_cash),
        "book_count": len(report_books),
    }


def fetch_autonomy_accounts_list(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Fetch list of accounts with book summary."""
    result = []
    for account in AccountRepository(conn).fetch_all():
        report_books = list_report_books(conn, account_id=account.id)
        result.append(_build_account_overview(conn, account, report_books))
    return result


def _fetch_account_books(conn: sqlite3.Connection, report_books: ReportBooks) -> list[dict[str, Any]]:
    """Build the per-book panel from the account's non-default books and their latest metrics."""
    result = []
    for book, assignment in report_books:
        latest_metrics_rows = DailyMetricsRepository(conn).fetch_for_book(book_id=book.id, limit=1)

        if latest_metrics_rows:
            m = latest_metrics_rows[0]
            latest_metrics: dict[str, Any] = {
                "hit_rate": m.hit_rate,
                "drawdown_pct": m.drawdown_pct,
                "trade_count": m.trade_count or 0,
                "metric_date": m.metric_date,
            }
        else:
            latest_metrics = {
                "hit_rate": None,
                "drawdown_pct": None,
                "trade_count": 0,
                "metric_date": None,
            }

        start_equity = book.start_equity or 0.0
        curr_equity = book.current_equity or 0.0
        curr_cash = book.current_cash or 0.0

        result.append(
            {
                "book_id": book.id,
                "name": book.name,
                "status": book.status or "active",
                "strategy": assignment.strategy_name if assignment is not None else "unassigned",
                "start_equity": start_equity,
                "current_equity": round(curr_equity, 2),
                "current_cash": round(curr_cash, 2),
                "return_pct": _return_pct(curr_equity, start_equity),
                "latest_metrics": latest_metrics,
            }
        )

    return result


def _fetch_recent_rotations(conn: sqlite3.Connection, report_books: ReportBooks) -> list[dict[str, Any]]:
    """Fetch recent rotation decisions for the account's books."""
    all_rotations = []
    for book, _assignment in report_books:
        rotation_rows = RotationDecisionRepository(conn).fetch_for_book(book_id=book.id, limit=20)

        for rotation_row in rotation_rows:
            all_rotations.append(
                {
                    "rotation_id": rotation_row.id,
                    "book_id": book.id,
                    "book_name": book.name,
                    "old_strategy": rotation_row.incumbent_strategy or "—",
                    "new_strategy": rotation_row.challenger_strategy or "—",
                    "decision_time": rotation_row.decision_time,
                    "reason": rotation_row.decision_reason or "—",
                }
            )

    all_rotations.sort(key=lambda row: str(row["decision_time"]), reverse=True)
    return all_rotations[:20]


def _fetch_risk_summary(conn: sqlite3.Connection, account_id: int) -> dict[str, Any]:
    """Fetch risk gate decisions and violations."""
    risk_records = RiskDecisionRepository(conn).fetch_recent(account_id=account_id, limit=100)

    violations = []
    kill_switch_triggered = False

    for rec in risk_records:
        if rec.action == "block":
            kill_switch_triggered = True

        violations.append(
            {
                "decision_id": rec.id,
                "symbol": rec.symbol or "unknown",
                "side": rec.side or "—",
                "action": rec.action or "allow",
                "reason": rec.reason_code or "—",
                "notional_usd": rec.approved_notional or 0.0,
                "max_notional_usd": rec.requested_notional or 0.0,
            }
        )

    return {
        "kill_switch_triggered": kill_switch_triggered,
        "violations": violations,
    }


def fetch_autonomy_account_detail(
    conn: sqlite3.Connection,
    account_name: str,
) -> dict[str, Any]:
    """Fetch all database-sourced data for a managed account's dashboard.

    Returns account overview, books, recent rotations, and risk summary.
    Uses repositories for all data access.

    Raises NotFoundError if account not found.
    """
    account = AccountRepository(conn).fetch_by_name(account_name=account_name)
    if account is None:
        raise NotFoundError(f"Account not found: {account_name}")

    report_books = list_report_books(conn, account_id=account.id)
    account_data = {
        "account": _build_account_overview(conn, account, report_books),
        "books": _fetch_account_books(conn, report_books),
        "recent_rotations": _fetch_recent_rotations(conn, report_books),
        "risk_summary": _fetch_risk_summary(conn, account.id),
    }

    return account_data
