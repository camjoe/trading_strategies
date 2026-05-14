"""Queries for IBKR paper account monitoring data.

Uses repository layer functions for all data access.
Also handles artifact I/O (daily runs, governance, burn-in status).
"""

from __future__ import annotations

import sqlite3
from typing import Any

from trading.repositories import accounts, sleeves, daily_metrics, rotation_decisions, sleeve_risk_decisions


def fetch_ibkr_paper_accounts_list(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Fetch list of IBKR paper accounts with sleeve summary."""
    # Get all accounts
    all_accounts = accounts.fetch_account_rows(conn)

    result = []
    for account in all_accounts:
        # Filter for managed accounts (IBKR paper accounts)
        if account.account_kind != "managed":
            continue

        # Get sleeves for this account
        account_sleeves = sleeves.fetch_strategy_sleeves_for_account(
            conn, account_id=account.id
        )

        # Calculate totals
        total_equity = sum(s["current_equity"] for s in account_sleeves)
        total_cash = sum(s["current_cash"] for s in account_sleeves)
        return_pct = (
            ((total_equity - account.initial_cash) / account.initial_cash * 100)
            if account.initial_cash
            else 0.0
        )

        result.append({
            "account_id": account.id,
            "name": account.name,
            "initial_cash": account.initial_cash,
            "total_equity": round(total_equity, 2),
            "total_cash": round(total_cash, 2),
            "positions_market_value": round(total_equity - total_cash, 2),
            "return_pct": round(return_pct, 2),
            "sleeve_count": len(account_sleeves),
        })

    return result


def _fetch_account_sleeves(conn: sqlite3.Connection, account_id: int) -> list[dict[str, Any]]:
    """Fetch all sleeves for an account with their latest metrics."""
    # Get sleeves
    sleeve_rows = sleeves.fetch_strategy_sleeves_for_account(conn, account_id=account_id)

    result = []
    for sleeve_row in sleeve_rows:
        sleeve_id = sleeve_row["id"]

        # Get latest metrics for this sleeve
        latest_metrics_rows = daily_metrics.fetch_daily_metrics_for_sleeve(
            conn, sleeve_id=sleeve_id, limit=1
        )

        latest_metrics = None
        if latest_metrics_rows:
            m = latest_metrics_rows[0]
            latest_metrics = {
                "hit_rate": m["hit_rate"],
                "drawdown_pct": m["drawdown_pct"],
                "trade_count": m["trade_count"] or 0,
                "metric_date": m["metric_date"],
            }
        else:
            latest_metrics = {
                "hit_rate": None,
                "drawdown_pct": None,
                "trade_count": 0,
                "metric_date": None,
            }

        # Calculate return
        start_equity = sleeve_row["start_equity"] or 0.0
        curr_equity = sleeve_row["current_equity"] or 0.0
        return_pct = (
            ((curr_equity - start_equity) / start_equity * 100)
            if start_equity
            else 0.0
        )

        result.append({
            "sleeve_id": sleeve_id,
            "name": sleeve_row["name"],
            "status": sleeve_row["status"] or "active",
            "strategy": "unknown",  # Would need sleeve_strategy_assignments query
            "start_equity": start_equity,
            "current_equity": round(curr_equity, 2),
            "current_cash": round(sleeve_row["current_cash"] or 0.0, 2),
            "return_pct": round(return_pct, 2),
            "latest_metrics": latest_metrics,
        })

    return result


def _fetch_recent_rotations(conn: sqlite3.Connection, account_id: int) -> list[dict[str, Any]]:
    """Fetch recent rotation decisions for account."""
    # Get sleeves for account
    sleeve_rows = sleeves.fetch_strategy_sleeves_for_account(conn, account_id=account_id)

    all_rotations = []
    for sleeve_row in sleeve_rows:
        sleeve_id = sleeve_row["id"]
        # Get rotation decisions for this sleeve
        rotation_rows = rotation_decisions.fetch_rotation_decisions_for_sleeve(
            conn, sleeve_id=sleeve_id, limit=20
        )

        for rotation_row in rotation_rows:
            all_rotations.append({
                "rotation_id": rotation_row["id"],
                "sleeve_id": sleeve_id,
                "sleeve_name": sleeve_row["name"],
                "old_strategy": rotation_row["incumbent_strategy"] or "—",
                "new_strategy": rotation_row["challenger_strategy"] or "—",
                "decision_time": rotation_row["decision_time"],
                "reason": rotation_row["decision_reason"] or "—",
            })

    # Sort by decision_time descending and limit to 20 total
    all_rotations.sort(key=lambda x: x["decision_time"], reverse=True)
    return all_rotations[:20]


def _fetch_risk_summary(conn: sqlite3.Connection, account_id: int) -> dict[str, Any]:
    """Fetch risk gate decisions and violations."""
    # Get risk decisions
    risk_rows = sleeve_risk_decisions.fetch_sleeve_risk_decisions_for_account(
        conn, account_id=account_id, limit=100
    )

    violations = []
    kill_switch_triggered = False

    for risk_row in risk_rows:
        if risk_row["action"] == "block":
            kill_switch_triggered = True

        violations.append({
            "decision_id": risk_row["id"],
            "symbol": risk_row["symbol"] or "unknown",
            "side": risk_row["side"] or "—",
            "action": risk_row["action"] or "allow",
            "reason": risk_row["reason_code"] or "—",
            "notional_usd": risk_row["approved_notional"] or 0.0,
            "max_notional_usd": risk_row["requested_notional"] or 0.0,
        })

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

    Raises ValueError if account not found.
    """
    # Get account using repository
    account = accounts.fetch_account_by_name(conn, account_name)
    if account is None:
        raise ValueError(f"Account not found: {account_name}")

    # Fetch all data components
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
            "return_pct": round(
                ((total_equity - account.initial_cash) / account.initial_cash * 100), 2
            )
            if account.initial_cash
            else 0.0,
            "sleeve_count": len(sleeve_list),
        },
        "sleeves": sleeve_list,
        "recent_rotations": _fetch_recent_rotations(conn, account.id),
        "risk_summary": _fetch_risk_summary(conn, account.id),
    }

    return account_data
