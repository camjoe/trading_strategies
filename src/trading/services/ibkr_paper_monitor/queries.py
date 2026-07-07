"""Queries for IBKR paper account monitoring data.

Uses repository layer functions for all data access.
Also handles artifact I/O (daily runs, governance, burn-in status).
"""

from __future__ import annotations

import sqlite3
from typing import Any

from trading.domain.exceptions import NotFoundError
from trading.repositories.book_bridge import book_id_for_sleeve
from trading.repositories.books import BookRepository
from trading.repositories.rotation_decisions import RotationDecisionRepository
from trading.repositories.daily_metrics import DailyMetricsRepository
from trading.repositories.accounts import AccountRepository
from trading.repositories.sleeve_risk_decisions import SleeveRiskDecisionRepository
from trading.repositories.sleeves import SleeveRepository


def fetch_ibkr_paper_accounts_list(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Fetch list of IBKR paper accounts with sleeve summary."""
    all_accounts = AccountRepository(conn).fetch_all()

    result = []
    for account in all_accounts:
        if account.account_kind != "managed":
            continue

        account_sleeves = SleeveRepository(conn).fetch_for_account(account_id=account.id)

        # Account totals come from the book balances (the sleeve balances freeze once
        # submission moves to the book path); Σ book equity/cash is the account roll-up.
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
                "sleeve_count": len(account_sleeves),
            }
        )

    return result


def _fetch_account_sleeves(conn: sqlite3.Connection, account_id: int) -> list[dict[str, Any]]:
    """Fetch all sleeves for an account with their latest metrics."""
    sleeve_records = SleeveRepository(conn).fetch_for_account(account_id=account_id)

    result = []
    for sleeve in sleeve_records:
        latest_metrics_rows = DailyMetricsRepository(conn).fetch_for_sleeve(sleeve_id=sleeve.id, limit=1)

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

        # Live equity/cash come from the sleeve's bridging book; fall back to the
        # sleeve's own values if it has never traded (no book yet).
        book_id = book_id_for_sleeve(conn, sleeve.id, create=False)
        book = BookRepository(conn).fetch_by_id(book_id=book_id) if book_id is not None else None
        start_equity = sleeve.start_equity or 0.0
        curr_equity = book.current_equity if book is not None else (sleeve.current_equity or 0.0)
        curr_cash = book.current_cash if book is not None else (sleeve.current_cash or 0.0)
        return_pct = ((curr_equity - start_equity) / start_equity * 100) if start_equity else 0.0

        result.append(
            {
                "sleeve_id": sleeve.id,
                "name": sleeve.name,
                "status": sleeve.status or "active",
                "strategy": "unknown",  # Would need sleeve_strategy_assignments query
                "start_equity": start_equity,
                "current_equity": round(curr_equity, 2),
                "current_cash": round(curr_cash, 2),
                "return_pct": round(return_pct, 2),
                "latest_metrics": latest_metrics,
            }
        )

    return result


def _fetch_recent_rotations(conn: sqlite3.Connection, account_id: int) -> list[dict[str, Any]]:
    """Fetch recent rotation decisions for account."""
    sleeve_records = SleeveRepository(conn).fetch_for_account(account_id=account_id)

    all_rotations = []
    for sleeve in sleeve_records:
        rotation_rows = RotationDecisionRepository(conn).fetch_for_sleeve(sleeve_id=sleeve.id, limit=20)

        for rotation_row in rotation_rows:
            all_rotations.append(
                {
                    "rotation_id": rotation_row["id"],
                    "sleeve_id": sleeve.id,
                    "sleeve_name": sleeve.name,
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
    risk_records = SleeveRiskDecisionRepository(conn).fetch_for_account(account_id=account_id, limit=100)

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

    Returns account overview, sleeves, recent rotations, and risk summary.
    Uses repositories for all data access.

    Raises NotFoundError if account not found.
    """
    account = AccountRepository(conn).fetch_by_name(account_name)
    if account is None:
        raise NotFoundError(f"Account not found: {account_name}")

    sleeve_list = _fetch_account_sleeves(conn, account.id)
    total_equity = sum(s["current_equity"] for s in sleeve_list)
    total_cash = sum(s["current_cash"] for s in sleeve_list)

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
            "sleeve_count": len(sleeve_list),
        },
        "sleeves": sleeve_list,
        "recent_rotations": _fetch_recent_rotations(conn, account.id),
        "risk_summary": _fetch_risk_summary(conn, account.id),
    }

    return account_data
