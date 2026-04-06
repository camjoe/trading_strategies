"""Manual trade injection endpoints.

POST /api/accounts/{account_name}/trades — insert a manual trade record for
a managed or virtual (test_account) paper-trading account.
"""
from __future__ import annotations

from common.time import utc_now_iso
from fastapi import APIRouter, HTTPException

from ..config import TEST_ACCOUNT_NAME
from ..schemas import ManualTradeRequest
from ..services import add_manual_trade, db_conn, resolve_backtest_payload_account

router = APIRouter()


@router.post("/api/accounts/{account_name}/trades")
def api_add_trade(account_name: str, body: ManualTradeRequest) -> dict[str, str]:
    """Insert a manual trade record for the given account.

    If *account_name* is the virtual ``test_account``, the trade is routed to
    its backing DB account (resolved via ``resolve_backtest_payload_account``).
    All other account names are used as-is.

    Returns ``{"status": "ok"}`` on success; raises ``HTTPException`` 404 if
    the account does not exist.
    """
    with db_conn() as conn:
        # test_account is virtual; route its trades to the backing DB account.
        if account_name == TEST_ACCOUNT_NAME:
            resolved_name = resolve_backtest_payload_account(account_name, conn)
        else:
            resolved_name = account_name

        try:
            add_manual_trade(
                conn,
                account_name=resolved_name,
                ticker=body.ticker.strip().upper(),
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
