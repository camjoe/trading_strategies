from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from trading.backtesting.backtest import (
    backtest_report_full,
    preview_backtest_warnings,
    run_backtest,
    run_walk_forward_backtest,
)

from ..schemas import BacktestPreflightRequest, BacktestRunRequest, WalkForwardRunRequest
from ..services.accounts.backtests import (
    fetch_latest_backtest_summary,
    fetch_recent_backtest_run_summaries,
)
from ..services.accounts.data_access import require_account_row
from ..services.backtests import (
    build_backtest_config_from_preflight_request,
    build_backtest_config_from_run_request,
    build_walk_forward_config_from_request,
)
from ..services.db import db_conn

router = APIRouter()


@router.get("/api/backtests/runs")
def api_backtest_runs(limit: int = Query(default=50, ge=1, le=500)) -> dict[str, list[dict[str, object]]]:
    with db_conn() as conn:
        return {"runs": fetch_recent_backtest_run_summaries(conn, limit=limit)}


@router.get("/api/backtests/latest/{account_name}")
def api_latest_backtest_for_account(account_name: str) -> dict[str, object]:
    with db_conn() as conn:
        resolved_account_name = account_name.strip()
        require_account_row(conn, resolved_account_name)
        latest = fetch_latest_backtest_summary(conn, resolved_account_name)
        return {"accountName": resolved_account_name, "latestRun": latest}


@router.get("/api/backtests/runs/{run_id}")
def api_backtest_run_report(run_id: int) -> dict[str, object]:
    with db_conn() as conn:
        # NotFoundError -> 404 is handled by the app-level exception handler.
        return backtest_report_full(conn, run_id).to_payload()


@router.post("/api/backtests/run")
def api_run_backtest(payload: BacktestRunRequest) -> dict[str, object]:
    with db_conn() as conn:
        resolved_account_name = payload.account.strip()
        payload = payload.model_copy(update={"account": resolved_account_name})
        # ValidationError -> 400 and NotFoundError -> 404 are handled by app-level
        # handlers; an unexpected ValueError surfaces as 500 (docs/adr/007-ui-error-mapping.md).
        result = run_backtest(conn, build_backtest_config_from_run_request(payload))
        return result.to_payload()


@router.post("/api/backtests/preflight")
def api_backtest_preflight(payload: BacktestPreflightRequest) -> dict[str, object]:
    with db_conn() as conn:
        resolved_account_name = payload.account.strip()
        payload = payload.model_copy(update={"account": resolved_account_name})
        try:
            warnings = preview_backtest_warnings(conn, build_backtest_config_from_preflight_request(payload))
        except FileNotFoundError as error:
            # A missing tickers file is a route-specific transport error, not a
            # domain validation failure — keep the direct 400 mapping here.
            raise HTTPException(status_code=400, detail=str(error)) from error

        # ValidationError -> 400 and NotFoundError -> 404 are handled by app-level
        # handlers; an unexpected ValueError surfaces as 500 (docs/adr/007-ui-error-mapping.md).
        return {"warnings": warnings}


@router.post("/api/backtests/walk-forward")
def api_run_walk_forward(payload: WalkForwardRunRequest) -> dict[str, object]:
    with db_conn() as conn:
        resolved_account_name = payload.account.strip()
        payload = payload.model_copy(update={"account": resolved_account_name})
        # ValidationError -> 400 and NotFoundError -> 404 are handled by app-level
        # handlers; an unexpected ValueError surfaces as 500 (docs/adr/007-ui-error-mapping.md).
        summary = run_walk_forward_backtest(conn, build_walk_forward_config_from_request(payload))
        return summary.to_payload()
