"""Analysis routes — per-account performance analysis endpoint."""
from __future__ import annotations

from fastapi import APIRouter

from ..services.db import db_conn
from ..services.test_account import fetch_resolved_account_row
from trading.services.analysis import fetch_account_analysis

router = APIRouter()


@router.get("/api/accounts/{account_name}/analysis")
def api_account_analysis(account_name: str) -> dict[str, object]:
    with db_conn() as conn:
        account = fetch_resolved_account_row(conn, account_name)
        return fetch_account_analysis(conn, account_row=account)
