"""Queries for IBKR paper account monitoring data.

Uses repository layer functions for all data access.
Also handles artifact I/O (daily runs, governance, burn-in status).
"""

from __future__ import annotations

import sqlite3
from typing import Any

from trading.domain.exceptions import NotFoundError
from trading.repositories.accounts import AccountRepository
from trading.repositories.books import BookRepository
from trading.repositories.daily_metrics import DailyMetricsRepository
from trading.repositories.rotation_decisions import RotationDecisionRepository
from trading.repositories.risk import RiskDecisionRepository
from trading.services.sleeves.book_assignments import list_report_books


def fetch_ibkr_paper_accounts_list(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Fetch list of IBKR paper accounts with book summary."""
    all_accounts = AccountRepository(conn).fetch_all()

    result = []
    for account in all_accounts:
        if account.account_kind != "managed":
            continue

        # Account totals are the Σ over the account's book balances.
        account_books = BookRepository(conn).fetch_for_account(account_id=account.id)
        total_equity = sum(b.current_equity for b in account_books)
        total_cash = sum(b.current_cash for b in account_books)
        return_pct = (
            ((total_equity - account.initial_cash) / account.initial_cash * 100) if account.initial_cash else 0.0
        )

        result.append(
            {
                "account_id": account.id,
                "name": account.name,
                "initial_cash": account.initial_cash,
                "total_equity": round(total_equity, 2),
                "total_cash": round(total_cash, 2),
                "positions_market_value": round(total_equity - total_cash, 2),
                "return_pct": round(return_pct, 2),
                "book_count": len(list_report_books(conn, account_id=account.id)),
            }
        )

    return result


def _fetch_account_books(conn: sqlite3.Connection, account_id: int) -> list[dict[str, Any]]:
    """Fetch all non-default books for an account with their latest metrics."""
    result = []
    for book, assignment in list_report_books(conn, account_id=account_id):
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
        return_pct = ((curr_equity - start_equity) / start_equity * 100) if start_equity else 0.0

        result.append(
            {
                "book_id": book.id,
                "name": book.name,
                "status": book.status or "active",
                "strategy": assignment.strategy_name if assignment is not None else "unassigned",
                "start_equity": start_equity,
                "current_equity": round(curr_equity, 2),
                "current_cash": round(curr_cash, 2),
                "return_pct": round(return_pct, 2),
                "latest_metrics": latest_metrics,
            }
        )

    return result


def _fetch_recent_rotations(conn: sqlite3.Connection, account_id: int) -> list[dict[str, Any]]:
    """Fetch recent rotation decisions for the account's books."""
    all_rotations = []
    for book, _assignment in list_report_books(conn, account_id=account_id):
        rotation_rows = RotationDecisionRepository(conn).fetch_for_book(book_id=book.id, limit=20)

        for rotation_row in rotation_rows:
            all_rotations.append(
                {
                    "rotation_id": rotation_row["id"],
                    "book_id": book.id,
                    "book_name": book.name,
                    "old_strategy": rotation_row["incumbent_strategy"] or "—",
                    "new_strategy": rotation_row["challenger_strategy"] or "—",
                    "decision_time": rotation_row["decision_time"],
                    "reason": rotation_row["decision_reason"] or "—",
                }
            )

    all_rotations.sort(key=lambda x: x["decision_time"], reverse=True)
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


def fetch_ibkr_paper_account_detail(
    conn: sqlite3.Connection,
    account_name: str,
) -> dict[str, Any]:
    """Fetch all database-sourced data for IBKR paper account dashboard.

    Returns account overview, books, recent rotations, and risk summary.
    Uses repositories for all data access.

    Raises NotFoundError if account not found.
    """
    account = AccountRepository(conn).fetch_by_name(account_name)
    if account is None:
        raise NotFoundError(f"Account not found: {account_name}")

    book_list = _fetch_account_books(conn, account.id)
    total_equity = sum(b["current_equity"] for b in book_list)
    total_cash = sum(b["current_cash"] for b in book_list)

    account_data = {
        "account": {
            "account_id": account.id,
            "name": account.name,
            "initial_cash": account.initial_cash,
            "total_equity": round(total_equity, 2),
            "total_cash": round(total_cash, 2),
            "positions_market_value": round(total_equity - total_cash, 2),
            "return_pct": round(((total_equity - account.initial_cash) / account.initial_cash * 100), 2)
            if account.initial_cash
            else 0.0,
            "book_count": len(book_list),
        },
        "books": book_list,
        "recent_rotations": _fetch_recent_rotations(conn, account.id),
        "risk_summary": _fetch_risk_summary(conn, account.id),
    }

    return account_data
