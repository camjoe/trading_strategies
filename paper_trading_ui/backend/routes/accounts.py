from __future__ import annotations

from fastapi import APIRouter

from ..config import TEST_ACCOUNT_NAME
from ..services import (
    get_account_row,
    build_account_summary,
    build_comparison_account_payload,
    fetch_account_snapshot_rows,
    db_conn,
    fetch_account_trades,
    get_latest_backtest_metrics,
    get_latest_backtest_summary,
    get_managed_account_rows,
    resolve_backtest_payload_account,
    build_snapshot_payload,
    build_test_account_detail_payload,
    build_test_account_summary,
    build_trade_payload,
)

router = APIRouter()


@router.get("/api/accounts")
def api_accounts() -> dict[str, list[dict[str, object]]]:
    with db_conn() as conn:
        rows = get_managed_account_rows(conn)
        accounts = [build_account_summary(conn, row) for row in rows]
        accounts.append(build_test_account_summary())
        accounts.sort(key=lambda item: str(item["name"]))
        return {"accounts": accounts}


@router.get("/api/accounts/compare")
def api_accounts_compare() -> dict[str, list[dict[str, object]]]:
    with db_conn() as conn:
        comparison: list[dict[str, object]] = []
        for row in get_managed_account_rows(conn):
            summary = build_account_summary(conn, row)
            latest_backtest = get_latest_backtest_metrics(conn, str(row["name"]))
            comparison.append(build_comparison_account_payload(summary, latest_backtest))

        comparison.append(build_comparison_account_payload(build_test_account_summary(), None))
        comparison.sort(key=lambda item: str(item["name"]))
        return {"accounts": comparison}


@router.get("/api/accounts/{account_name}")
def api_account_detail(account_name: str) -> dict[str, object]:
    if account_name == TEST_ACCOUNT_NAME:
        payload = build_test_account_detail_payload()
        with db_conn() as conn:
            resolved_account_name = resolve_backtest_payload_account(account_name, conn)
            payload["latestBacktest"] = get_latest_backtest_summary(conn, resolved_account_name)
        return payload

    with db_conn() as conn:
        account = get_account_row(conn, account_name)
        summary = build_account_summary(conn, account)

        snapshots = fetch_account_snapshot_rows(conn, int(account["id"]), limit=100)

        trades = fetch_account_trades(conn, int(account["id"]))
        latest_backtest = get_latest_backtest_summary(conn, account_name)

        return {
            "account": summary,
            "latestBacktest": latest_backtest,
            "snapshots": [build_snapshot_payload(snapshot) for snapshot in snapshots],
            "trades": [build_trade_payload(trade) for trade in trades[-100:]],
        }

