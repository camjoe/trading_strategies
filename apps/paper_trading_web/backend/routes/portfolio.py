"""Portfolio routes — cross-account exposure and concentration rollup."""

from __future__ import annotations

from fastapi import APIRouter

from ..services.db import db_conn
from ..services.portfolio import build_portfolio_rollup_payload

router = APIRouter()


@router.get("/api/portfolio/rollup")
def api_portfolio_rollup() -> dict[str, object]:
    """Cross-account portfolio rollup: exposure per account plus symbol/sector concentration."""
    with db_conn() as conn:
        return build_portfolio_rollup_payload(conn)
