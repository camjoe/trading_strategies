from __future__ import annotations

from fastapi import APIRouter, HTTPException

from trading.services.accounting import list_account_trades
from trading.services.accounts import list_account_snapshots
from trading.services.market_data import build_provider

from ..account_options import get_account_config_options
from ..account_contract import build_account_params_update_command
from ..schemas import AccountParamsRequest
from ..services.accounts.backtests import (
    fetch_latest_backtest_metrics,
    fetch_latest_backtest_summary,
)
from ..services.accounts.benchmark import (
    attach_live_benchmark_summary,
    build_live_benchmark_overlay,
)
from ..services.accounts.data_access import (
    build_snapshot_payload,
    build_trade_payload,
    fetch_visible_account_rows,
    require_account_row,
)
from ..services.accounts.mutations import update_account_params
from ..services.accounts.summaries import (
    build_account_list_payload,
    build_account_summary,
    build_account_summary_and_positions,
    build_comparison_account_payload,
)
from ..services.db import db_conn

router = APIRouter()


@router.get("/api/accounts/config/options")
def api_account_config_options() -> dict[str, object]:
    """Return ordered option values and defaults for the account configuration editor."""
    return get_account_config_options()


@router.get("/api/accounts")
def api_accounts() -> dict[str, list[dict[str, object]]]:
    with db_conn() as conn:
        provider = build_provider()
        rows = fetch_visible_account_rows(conn)
        accounts = [build_account_list_payload(build_account_summary(conn, row, provider=provider)) for row in rows]
        accounts.sort(key=lambda item: str(item["name"]))
        return {"accounts": accounts}


@router.get("/api/accounts/compare")
def api_accounts_compare() -> dict[str, list[dict[str, object]]]:
    with db_conn() as conn:
        provider = build_provider()
        comparison: list[dict[str, object]] = []
        for row in fetch_visible_account_rows(conn):
            summary = build_account_summary(conn, row, provider=provider)
            snapshots = list_account_snapshots(conn, row.id, limit=100)
            attach_live_benchmark_summary(
                summary,
                build_live_benchmark_overlay(str(summary.get("benchmark") or ""), snapshots, provider=provider),
            )
            latest_backtest = fetch_latest_backtest_metrics(conn, row.name)
            comparison.append(build_comparison_account_payload(summary, latest_backtest))
        comparison.sort(key=lambda item: str(item["name"]))
        return {"accounts": comparison}


@router.get("/api/accounts/{account_name}")
def api_account_detail(account_name: str) -> dict[str, object]:
    with db_conn() as conn:
        provider = build_provider()
        account = require_account_row(conn, account_name)
        summary, positions = build_account_summary_and_positions(conn, account, provider=provider)

        snapshots = list_account_snapshots(conn, account.id, limit=100)
        overlay = build_live_benchmark_overlay(str(summary.get("benchmark") or ""), snapshots, provider=provider)
        attach_live_benchmark_summary(summary, overlay)
        trades = list_account_trades(conn, account.id)
        latest_backtest = fetch_latest_backtest_summary(conn, account.name)
        latest_backtest_metrics = fetch_latest_backtest_metrics(conn, account.name)

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
        require_account_row(conn, account_name)
        command = build_account_params_update_command(body)
        try:
            update_account_params(
                conn,
                account_name,
                command=command,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"status": "ok"}
