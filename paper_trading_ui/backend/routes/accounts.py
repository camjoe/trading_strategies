from __future__ import annotations

from fastapi import APIRouter, HTTPException

from common.coercion import row_expect_int

from ..account_options import get_account_config_options
from ..account_contract import build_account_params_update_command
from ..config import TEST_ACCOUNT_NAME, TEST_ACCOUNT_DISPLAY_NAME
from ..schemas import AccountParamsRequest
from ..services import (
    attach_live_benchmark_summary,
    build_account_list_payload,
    fetch_account_row,
    build_account_summary,
    build_account_summary_and_positions,
    build_comparison_account_payload,
    build_live_benchmark_overlay,
    db_conn,
    fetch_account_trades,
    fetch_latest_backtest_metrics,
    fetch_latest_backtest_summary,
    fetch_managed_account_rows,
    fetch_resolved_account_row,
    fetch_snapshot_history_rows,
    build_snapshot_payload,
    build_test_account_live_summary,
    build_trade_payload,
    update_account_params,
)

router = APIRouter()


@router.get("/api/accounts/config/options")
def api_account_config_options() -> dict[str, object]:
    return get_account_config_options()


@router.get("/api/accounts")
def api_accounts() -> dict[str, list[dict[str, object]]]:
    with db_conn() as conn:
        rows = fetch_managed_account_rows(conn)
        accounts = [build_account_list_payload(build_account_summary(conn, row)) for row in rows]
        accounts.append(build_account_list_payload(build_test_account_live_summary(conn)))
        accounts.sort(key=lambda item: str(item["name"]))
        return {"accounts": accounts}


@router.get("/api/accounts/compare")
def api_accounts_compare() -> dict[str, list[dict[str, object]]]:
    with db_conn() as conn:
        comparison: list[dict[str, object]] = []
        for row in fetch_managed_account_rows(conn):
            summary = build_account_summary(conn, row)
            snapshots = fetch_snapshot_history_rows(conn, row_expect_int(row, "id"), limit=100)
            attach_live_benchmark_summary(summary, build_live_benchmark_overlay(summary, snapshots))
            latest_backtest = fetch_latest_backtest_metrics(conn, str(row["name"]))
            comparison.append(build_comparison_account_payload(summary, latest_backtest))

        test_summary = build_test_account_live_summary(conn)
        test_account = fetch_resolved_account_row(conn, TEST_ACCOUNT_NAME)
        test_snapshots = fetch_snapshot_history_rows(conn, row_expect_int(test_account, "id"), limit=100)
        attach_live_benchmark_summary(test_summary, build_live_benchmark_overlay(test_summary, test_snapshots))
        comparison.append(build_comparison_account_payload(test_summary, None))
        comparison.sort(key=lambda item: str(item["name"]))
        return {"accounts": comparison}


@router.get("/api/accounts/{account_name}")
def api_account_detail(account_name: str) -> dict[str, object]:
    with db_conn() as conn:
        account = fetch_resolved_account_row(conn, account_name)
        summary, positions = build_account_summary_and_positions(conn, account)

        if account_name == TEST_ACCOUNT_NAME:
            summary["name"] = TEST_ACCOUNT_NAME
            summary["displayName"] = TEST_ACCOUNT_DISPLAY_NAME

        snapshots = fetch_snapshot_history_rows(conn, row_expect_int(account, "id"), limit=100)
        overlay = build_live_benchmark_overlay(summary, snapshots)
        attach_live_benchmark_summary(summary, overlay)
        trades = fetch_account_trades(conn, row_expect_int(account, "id"))
        latest_backtest = fetch_latest_backtest_summary(conn, str(account["name"]))
        latest_backtest_metrics = fetch_latest_backtest_metrics(conn, str(account["name"]))

        return {
            "account": summary,
            "positions": positions,
            "latestBacktest": latest_backtest,
            "latestBacktestMetrics": latest_backtest_metrics,
            "liveBenchmarkOverlay": overlay,
            "snapshots": [build_snapshot_payload(snapshot) for snapshot in snapshots],
            "trades": [build_trade_payload(trade) for trade in trades[-100:]],
        }


@router.patch("/api/accounts/{account_name}/params")
def api_update_account_params(account_name: str, body: AccountParamsRequest) -> dict[str, str]:
    """Partially update mutable account parameters.

    All fields are optional — omitted fields are left unchanged.

    Returns ``{"status": "ok"}`` on success.  Raises ``HTTPException`` if the
    account does not exist.
    """
    with db_conn() as conn:
        account = fetch_account_row(conn, account_name)
        command = build_account_params_update_command(body)
        try:
            update_account_params(
                conn,
                row_expect_int(account, "id"),
                account_name,
                command=command,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"status": "ok"}
