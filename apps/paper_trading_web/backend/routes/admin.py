from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..account_contract import build_admin_create_account_command
from ..schemas import AdminCreateAccountRequest, AdminDeleteAccountRequest
from ..services.accounts.benchmark import attach_live_benchmark_summary
from ..services.accounts.data_access import require_account_row
from ..services.accounts.summaries import build_account_summary
from ..services.admin import (
    build_account_deletion_preview,
    create_account_with_rotation,
    delete_managed_account,
)
from ..services.db import db_conn
from ..services.exports import list_csv_exports, preview_csv_export
from ..services.operations import list_operations_overview
from ..services.promotion import build_promotion_overview

router = APIRouter()


@router.post("/api/admin/accounts/create")
def api_admin_create_account(payload: AdminCreateAccountRequest) -> dict[str, object]:
    command = build_admin_create_account_command(payload)
    with db_conn() as conn:
        # ValidationError (bad input or duplicate name) -> 400 via the app-level
        # handler; an unexpected ValueError surfaces as 500 (docs/adr/007-ui-error-mapping.md).
        create_account_with_rotation(conn, command)

        account = require_account_row(conn, command.name)
        summary = build_account_summary(conn, account)
        attach_live_benchmark_summary(summary, None)
        return {"status": "ok", "account": summary}


@router.post("/api/admin/accounts/delete")
def api_admin_delete_account(payload: AdminDeleteAccountRequest) -> dict[str, object]:
    if not payload.confirm:
        raise HTTPException(status_code=400, detail="Deletion requires explicit confirmation.")

    deleted_name = delete_managed_account(payload.accountName)
    return {"status": "ok", "deleted": {"accountName": deleted_name}}


@router.get("/api/admin/accounts/delete-preview")
def api_admin_delete_account_preview(accountName: str = Query(..., min_length=1)) -> dict[str, object]:  # noqa: N803
    """Return account identity details for confirmation before deletion."""
    return {"status": "ok", "preview": build_account_deletion_preview(accountName)}


@router.get("/api/admin/exports/csv")
def api_csv_exports() -> dict[str, object]:
    return list_csv_exports()


@router.get("/api/admin/operations/overview")
def api_operations_overview() -> dict[str, object]:
    """Return current runtime job health, recent artifacts, and backup visibility."""
    return list_operations_overview()


@router.get("/api/admin/promotion/overview")
def api_promotion_overview(
    accountName: str = Query(..., min_length=1),  # noqa: N803
    strategyName: str | None = Query(default=None),  # noqa: N803
    limit: int = Query(default=5, ge=1, le=20),
) -> dict[str, object]:
    """Return promotion readiness plus persisted review history for one account."""
    with db_conn() as conn:
        # A missing account raises NotFoundError (from get_account), mapped to 404
        # by the app-level handler; an unexpected ValueError surfaces as 500.
        # See docs/adr/007-ui-error-mapping.md.
        return build_promotion_overview(
            conn,
            account_name=accountName.strip(),
            strategy_name=strategyName,
            limit=limit,
        )


@router.get("/api/admin/exports/csv/preview")
def api_csv_export_preview(
    exportName: str = Query(..., min_length=1),  # noqa: N803
    fileName: str = Query(..., min_length=1),  # noqa: N803
    limit: int = Query(default=200, ge=1, le=2000),
) -> dict[str, object]:
    return preview_csv_export(exportName, fileName, limit)
