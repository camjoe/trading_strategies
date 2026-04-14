from __future__ import annotations

from fastapi import APIRouter

from ..config import TEST_ACCOUNT_NAME
from ..services import fetch_account_names, fetch_account_row, db_conn, take_snapshot

router = APIRouter()


@router.post("/api/actions/snapshot/{account_name}")
def api_snapshot(account_name: str) -> dict[str, str]:
    if account_name == TEST_ACCOUNT_NAME:
        return {"status": "ok", "message": "TEST Account snapshot is virtual."}

    with db_conn() as conn:
        fetch_account_row(conn, account_name)
        take_snapshot(conn, account_name, snapshot_time=None)
        return {"status": "ok", "message": f"Snapshot saved for {account_name}"}


@router.post("/api/actions/snapshot-all")
def api_snapshot_all() -> dict[str, object]:
    with db_conn() as conn:
        names = fetch_account_names(conn)
        for name in names:
            take_snapshot(conn, name, snapshot_time=None)
        return {"status": "ok", "snapshotted": names + [TEST_ACCOUNT_NAME]}

