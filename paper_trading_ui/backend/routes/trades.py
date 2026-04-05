from __future__ import annotations

from common.time import utc_now_iso
from fastapi import APIRouter

from ..config import TEST_ACCOUNT_NAME
from ..schemas import ManualTradeRequest
from ..services import db_conn, fetch_account_row, resolve_backtest_payload_account
from trading.repositories.trades_repository import insert_trade

router = APIRouter()


@router.post("/api/accounts/{account_name}/trades")
def api_add_trade(account_name: str, body: ManualTradeRequest) -> dict[str, str]:
    with db_conn() as conn:
        # test_account is virtual; route its trades to the backing DB account.
        if account_name == TEST_ACCOUNT_NAME:
            resolved_name = resolve_backtest_payload_account(account_name, conn)
        else:
            resolved_name = account_name

        account = fetch_account_row(conn, resolved_name)
        insert_trade(
            conn,
            account_id=int(account["id"]),
            ticker=body.ticker.strip().upper(),
            side=body.side,
            qty=body.qty,
            price=body.price,
            fee=body.fee,
            trade_time=utc_now_iso(),
            note=None,
        )
    return {"status": "ok"}
