from __future__ import annotations

from fastapi import APIRouter

from trading.reporting import snapshot_account

from ..config import TEST_ACCOUNT_NAME
from ..services import get_account_row, db_conn

router = APIRouter()


@router.post("/api/actions/snapshot/{account_name}")
def api_snapshot(account_name: str) -> dict[str, str]:
    if account_name == TEST_ACCOUNT_NAME:
        return {"status": "ok", "message": "TEST Account snapshot is virtual."}

    with db_conn() as conn:
        get_account_row(conn, account_name)
        snapshot_account(conn, account_name, snapshot_time=None)
        return {"status": "ok", "message": f"Snapshot saved for {account_name}"}


@router.post("/api/actions/snapshot-all")
def api_snapshot_all() -> dict[str, object]:
    with db_conn() as conn:
        rows = conn.execute("SELECT name FROM accounts ORDER BY name").fetchall()
        names = [str(row["name"]) for row in rows]
        for name in names:
            snapshot_account(conn, name, snapshot_time=None)
        return {"status": "ok", "snapshotted": names + [TEST_ACCOUNT_NAME]}

