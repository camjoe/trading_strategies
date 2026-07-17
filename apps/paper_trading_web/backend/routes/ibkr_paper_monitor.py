"""API routes for IBKR paper account autonomy monitoring dashboard."""

from __future__ import annotations

from fastapi import APIRouter

from ..services.db import db_conn
from ..services.ibkr_paper_monitor import (
    fetch_account_ibkr_paper_monitor_data,
    fetch_ibkr_paper_accounts_list,
)

router = APIRouter()


@router.get("/api/ibkr-paper-accounts")
def api_ibkr_paper_accounts() -> dict[str, object]:
    """Return list of IBKR paper accounts with book summary and latest run status."""
    with db_conn() as conn:
        accounts = fetch_ibkr_paper_accounts_list(conn)
        return {"accounts": accounts}


@router.get("/api/ibkr-paper-accounts/{account_name}")
def api_ibkr_paper_account_detail(account_name: str) -> dict[str, object]:
    """Return comprehensive IBKR paper account dashboard data.

    Includes:
    - Account overview (total equity, cash, positions)
    - Book status and performance metrics
    - Latest daily workflow run details
    - Governance check status (W1-W3, M1-M3)
    - Burn-in progress
    - Recent rotations
    - Risk summary (kill switch, violations)
    """
    with db_conn() as conn:
        # NotFoundError -> 404 is handled by the app-level exception handler.
        return fetch_account_ibkr_paper_monitor_data(conn, account_name)
