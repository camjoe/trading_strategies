from __future__ import annotations

from fastapi import APIRouter

from trading.services.reporting import snapshot_account

from ..services.accounts.data_access import require_account_row
from ..services.db import db_conn
from trading.services.accounts import list_account_names

router = APIRouter()


@router.post("/api/actions/snapshot/{account_name}")
def api_snapshot(account_name: str) -> dict[str, str]:
    with db_conn() as conn:
        requested_name = account_name.strip()
        require_account_row(conn, requested_name)
        snapshot_account(conn, requested_name, snapshot_time=None)
        return {"status": "ok", "message": f"Snapshot saved for {requested_name}"}


@router.post("/api/actions/snapshot-all")
def api_snapshot_all() -> dict[str, object]:
    with db_conn() as conn:
        names = list_account_names(conn)
        for name in names:
            snapshot_account(conn, name, snapshot_time=None)
        return {"status": "ok", "snapshotted": names}
