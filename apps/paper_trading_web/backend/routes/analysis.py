"""Analysis routes — per-account performance analysis endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from ..services.accounts.data_access import require_account_row
from ..services.db import db_conn
from trading.services.analysis import fetch_account_analysis
from trading.services.market_data import build_provider

router = APIRouter()


@router.get("/api/accounts/{account_name}/analysis")
def api_account_analysis(account_name: str) -> dict[str, object]:
    with db_conn() as conn:
        account = require_account_row(conn, account_name)
        return fetch_account_analysis(conn, account_row=account, provider=build_provider())
