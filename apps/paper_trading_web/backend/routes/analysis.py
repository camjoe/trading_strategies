"""Analysis routes — per-account performance analysis endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from infrastructure.market_data.factory import build_provider
from trading.services.analysis.queries import fetch_account_analysis

from ..services.accounts.data_access import require_account_row
from ..services.db import db_conn
from ..services.shaping import camelize_keys

router = APIRouter()


@router.get("/api/accounts/{account_name}/analysis")
def api_account_analysis(account_name: str) -> dict[str, object]:
    with db_conn() as conn:
        account = require_account_row(conn, account_name)
        # Analysis returns a snake_case domain payload; the boundary camelCases it.
        return camelize_keys(fetch_account_analysis(conn, account_row=account, provider=build_provider()))
