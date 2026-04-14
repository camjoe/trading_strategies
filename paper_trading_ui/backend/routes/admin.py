from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..account_contract import build_admin_create_account_command
from ..schemas import AdminCreateAccountRequest, AdminDeleteAccountRequest
from ..services import (
    fetch_account_row,
    build_account_summary,
    db_conn,
    delete_account_and_dependents,
    list_csv_exports,
    preview_csv_export,
)
from ..config import TEST_ACCOUNT_NAME
from trading.services.accounts_service import create_account
from trading.domain import AccountAlreadyExistsError
from trading.services.profiles_service import apply_rotation_fields

router = APIRouter()


@router.post("/api/admin/accounts/create")
def api_admin_create_account(payload: AdminCreateAccountRequest) -> dict[str, object]:
    command = build_admin_create_account_command(payload)
    with db_conn() as conn:
        try:
            create_account(
                conn,
                name=command.name,
                strategy=command.strategy,
                initial_cash=command.initial_cash,
                benchmark_ticker=command.benchmark_ticker,
                config=command.config,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except AccountAlreadyExistsError as error:
            raise HTTPException(status_code=400, detail=f"Account create failed: {error}") from error

        apply_rotation_fields(conn, command.name, command.rotation_profile)

        account = fetch_account_row(conn, command.name)
        return {"status": "ok", "account": build_account_summary(conn, account)}


@router.post("/api/admin/accounts/delete")
def api_admin_delete_account(payload: AdminDeleteAccountRequest) -> dict[str, object]:
    if not payload.confirm:
        raise HTTPException(status_code=400, detail="Deletion requires explicit confirmation.")

    if payload.accountName.strip() == TEST_ACCOUNT_NAME:
        raise HTTPException(status_code=400, detail="TEST Account is virtual and cannot be deleted.")

    counts = delete_account_and_dependents(payload.accountName.strip())
    return {"status": "ok", "deleted": counts}


@router.get("/api/admin/exports/csv")
def api_csv_exports() -> dict[str, object]:
    return list_csv_exports()


@router.get("/api/admin/exports/csv/preview")
def api_csv_export_preview(
    exportName: str = Query(..., min_length=1),
    fileName: str = Query(..., min_length=1),
    limit: int = Query(default=200, ge=1, le=2000),
) -> dict[str, object]:
    return preview_csv_export(exportName, fileName, limit)
