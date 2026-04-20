from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from trading.backtesting.backtest import (
    backtest_report_full,
    preview_backtest_warnings,
    run_backtest,
    run_walk_forward_backtest,
)

from ..schemas import BacktestPreflightRequest, BacktestRunRequest, WalkForwardRunRequest
from ..services import (
    fetch_account_row,
    build_backtest_config_from_preflight_request,
    build_backtest_config_from_run_request,
    fetch_recent_backtest_run_summaries,
    db_conn,
    display_account_name,
    fetch_latest_backtest_summary,
    resolve_backtest_payload_account,
    build_walk_forward_config_from_request,
)

router = APIRouter()


@router.get("/api/backtests/runs")
def api_backtest_runs(limit: int = Query(default=50, ge=1, le=500)) -> dict[str, list[dict[str, object]]]:
    with db_conn() as conn:
        return {"runs": fetch_recent_backtest_run_summaries(conn, limit=int(limit))}


@router.get("/api/backtests/latest/{account_name}")
def api_latest_backtest_for_account(account_name: str) -> dict[str, object]:
    with db_conn() as conn:
        resolved_account_name = resolve_backtest_payload_account(account_name, conn)
        fetch_account_row(conn, resolved_account_name)
        latest = fetch_latest_backtest_summary(conn, resolved_account_name)
        return {"accountName": account_name, "latestRun": latest}


@router.get("/api/backtests/runs/{run_id}")
def api_backtest_run_report(run_id: int) -> dict[str, object]:
    with db_conn() as conn:
        try:
            return backtest_report_full(conn, run_id).to_payload()
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/api/backtests/run")
def api_run_backtest(payload: BacktestRunRequest) -> dict[str, object]:
    with db_conn() as conn:
        resolved_account_name = resolve_backtest_payload_account(payload.account, conn)
        payload = payload.model_copy(update={"account": resolved_account_name})
        try:
            result = run_backtest(conn, build_backtest_config_from_run_request(payload))
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

        return result.to_payload(display_name_fn=display_account_name)


@router.post("/api/backtests/preflight")
def api_backtest_preflight(payload: BacktestPreflightRequest) -> dict[str, object]:
    with db_conn() as conn:
        resolved_account_name = resolve_backtest_payload_account(payload.account, conn)
        payload = payload.model_copy(update={"account": resolved_account_name})
        try:
            warnings = preview_backtest_warnings(conn, build_backtest_config_from_preflight_request(payload))
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except FileNotFoundError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

        return {"warnings": warnings}


@router.post("/api/backtests/walk-forward")
def api_run_walk_forward(payload: WalkForwardRunRequest) -> dict[str, object]:
    with db_conn() as conn:
        resolved_account_name = resolve_backtest_payload_account(payload.account, conn)
        payload = payload.model_copy(update={"account": resolved_account_name})
        try:
            summary = run_walk_forward_backtest(conn, build_walk_forward_config_from_request(payload))
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

        return summary.to_payload(display_name_fn=display_account_name)
