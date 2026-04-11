"""Manual trade injection endpoints.

POST /api/accounts/{account_name}/trades — insert a manual trade record for
the virtual test_account only.  Manual trades are not permitted on managed
(strategy-driven) accounts.
"""
from __future__ import annotations

import common.market_data as _md
from common.time import utc_now_iso
from fastapi import APIRouter, HTTPException

from ..config import TEST_ACCOUNT_NAME
from ..schemas import ManualTradeRequest
from ..services import add_manual_trade, db_conn, resolve_backtest_payload_account

router = APIRouter()


def _ticker_exists(ticker: str) -> bool:
    """Return True if *ticker* has recent price history in the market data provider."""
    try:
        series = _md.get_provider().fetch_close_series(ticker, "5d")
        return series is not None and not series.empty
    except Exception:
        return False


@router.post("/api/accounts/{account_name}/trades")
def api_add_trade(account_name: str, body: ManualTradeRequest) -> dict[str, str]:
    """Insert a manual trade record for the test account.

    Manual trades are only permitted for the virtual ``test_account``.  All
    other account names are rejected with 403.

    Returns ``{"status": "ok"}`` on success.  Raises:
    - 403 if *account_name* is not ``test_account``
    - 400 if the ticker is not recognised by the market data provider
    - 404 if the resolved DB account does not exist
    - 400 for other business-rule violations (insufficient cash, oversell)
    """
    if account_name != TEST_ACCOUNT_NAME:
        raise HTTPException(
            status_code=403,
            detail="Manual trades are only permitted on the test account.",
        )

    ticker = body.ticker.strip().upper()
    if not _ticker_exists(ticker):
        raise HTTPException(
            status_code=400,
            detail=f"Ticker '{ticker}' was not found. Only recognised tickers may be traded.",
        )

    with db_conn() as conn:
        resolved_name = resolve_backtest_payload_account(account_name, conn)
        try:
            add_manual_trade(
                conn,
                account_name=resolved_name,
                ticker=ticker,
                side=body.side,
                qty=body.qty,
                price=body.price,
                fee=body.fee,
                trade_time=utc_now_iso(),
            )
        except ValueError as exc:
            # record_trade raises ValueError for both "not found" and business-rule
            # violations (insufficient cash, oversell).  Return 404 only for the
            # former; all other rejections are 400 Bad Request.
            status = 404 if "not found" in str(exc).lower() else 400
            raise HTTPException(status_code=status, detail=str(exc)) from exc
    return {"status": "ok"}
