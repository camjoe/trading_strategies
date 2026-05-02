from __future__ import annotations

from fastapi import APIRouter

from trading.services.reporting import snapshot_account

from ..config import TEST_ACCOUNT_NAME
from ..services.accounts.data_access import require_account_row
from ..services.db import db_conn
from ..services.test_account import ensure_test_account
from trading.services.accounts import RUNTIME_JOB_ELIGIBLE_ACCOUNT_KINDS, list_account_names

router = APIRouter()


@router.post("/api/actions/snapshot/{account_name}")
def api_snapshot(account_name: str) -> dict[str, str]:
    with db_conn() as conn:
        requested_name = account_name.strip()
        if requested_name == TEST_ACCOUNT_NAME:
            ensure_test_account(conn)
            snapshot_account(conn, TEST_ACCOUNT_NAME, snapshot_time=None)
            return {"status": "ok", "message": f"Snapshot saved for {TEST_ACCOUNT_NAME}"}

        require_account_row(conn, requested_name)
        snapshot_account(conn, requested_name, snapshot_time=None)
        return {"status": "ok", "message": f"Snapshot saved for {requested_name}"}


@router.post("/api/actions/snapshot-all")
def api_snapshot_all() -> dict[str, object]:
    with db_conn() as conn:
        names = list_account_names(conn, account_kinds=RUNTIME_JOB_ELIGIBLE_ACCOUNT_KINDS)
        for name in names:
            snapshot_account(conn, name, snapshot_time=None)
        return {"status": "ok", "snapshotted": names}
