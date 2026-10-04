"""API routes for the autonomy monitoring dashboard (managed accounts)."""

from __future__ import annotations

from fastapi import APIRouter

from ..services.autonomy_monitor import (
    fetch_autonomy_account_data,
    fetch_autonomy_accounts_list,
)
from ..services.db import db_conn

router = APIRouter()


@router.get("/api/autonomy/accounts")
def api_autonomy_accounts() -> dict[str, object]:
    """Return list of managed accounts with book summary and latest run status."""
    with db_conn() as conn:
        accounts = fetch_autonomy_accounts_list(conn)
        return {"accounts": accounts}


@router.get("/api/autonomy/accounts/{account_name}")
def api_autonomy_account_detail(account_name: str) -> dict[str, object]:
    """Return comprehensive autonomy dashboard data for a managed account.

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
        return fetch_autonomy_account_data(conn, account_name)
