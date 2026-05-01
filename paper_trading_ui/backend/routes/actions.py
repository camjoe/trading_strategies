from __future__ import annotations

from fastapi import APIRouter

from trading.services.reporting import snapshot_account

from ..config import TEST_ACCOUNT_NAME
from ..services.accounts.data_access import require_account_row
from ..services.db import db_conn
from ..services.test_account import resolve_backtest_payload_account
from trading.services.accounts import RUNTIME_JOB_ELIGIBLE_ACCOUNT_KINDS, list_account_names

router = APIRouter()


@router.post("/api/actions/snapshot/{account_name}")
def api_snapshot(account_name: str) -> dict[str, str]:
    with db_conn() as conn:
        resolved_name = resolve_backtest_payload_account(account_name, conn)
        require_account_row(conn, resolved_name)
        snapshot_account(conn, resolved_name, snapshot_time=None)
        message_name = TEST_ACCOUNT_NAME if account_name == TEST_ACCOUNT_NAME else resolved_name
        return {"status": "ok", "message": f"Snapshot saved for {message_name}"}


@router.post("/api/actions/snapshot-all")
def api_snapshot_all() -> dict[str, object]:
    with db_conn() as conn:
        names = list_account_names(conn, account_kinds=RUNTIME_JOB_ELIGIBLE_ACCOUNT_KINDS)
        for name in names:
            snapshot_account(conn, name, snapshot_time=None)
        return {"status": "ok", "snapshotted": names}
