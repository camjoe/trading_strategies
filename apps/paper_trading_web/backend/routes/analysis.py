"""Analysis routes — per-account performance analysis endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from infrastructure.market_data.factory import build_provider
from trading.services.analysis.queries import fetch_account_analysis

from ..services.accounts.data_access import require_account_row
from ..services.analysis import build_account_analysis_payload
from ..services.db import db_conn

router = APIRouter()


@router.get("/api/accounts/{account_name}/analysis")
def api_account_analysis(account_name: str) -> dict[str, object]:
    with db_conn() as conn:
        account = require_account_row(conn, account_name)
        # Analysis returns a snake_case domain payload; the boundary shapes camelCase.
        analysis = fetch_account_analysis(conn, account_row=account, provider=build_provider())
        return build_account_analysis_payload(analysis)
