"""Analysis routes — per-account performance analysis endpoint."""
from __future__ import annotations

from fastapi import APIRouter

from ..services import db_conn, fetch_account_row, resolve_backtest_payload_account
from trading.services.analysis_service import fetch_account_analysis

router = APIRouter()


@router.get("/api/accounts/{account_name}/analysis")
def api_account_analysis(account_name: str) -> dict[str, object]:
    with db_conn() as conn:
        resolved_name = resolve_backtest_payload_account(account_name, conn)
        account = fetch_account_row(conn, resolved_name)
        return fetch_account_analysis(conn, account_row=account)
