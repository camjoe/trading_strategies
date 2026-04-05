from __future__ import annotations

from fastapi import APIRouter

from ..config import TEST_ACCOUNT_NAME
from ..schemas import AccountParamsRequest
from ..services import (
    fetch_account_row,
    build_account_summary,
    build_comparison_account_payload,
    fetch_account_snapshot_rows,
    db_conn,
    fetch_account_trades,
    fetch_latest_backtest_metrics,
    fetch_latest_backtest_summary,
    fetch_managed_account_rows,
    resolve_backtest_payload_account,
    build_snapshot_payload,
    build_test_account_detail_payload,
    build_test_account_summary,
    build_trade_payload,
    update_account_params,
)

router = APIRouter()


@router.get("/api/accounts")
def api_accounts() -> dict[str, list[dict[str, object]]]:
    with db_conn() as conn:
        rows = fetch_managed_account_rows(conn)
        accounts = [build_account_summary(conn, row) for row in rows]
        accounts.append(build_test_account_summary())
        accounts.sort(key=lambda item: str(item["name"]))
        return {"accounts": accounts}


@router.get("/api/accounts/compare")
def api_accounts_compare() -> dict[str, list[dict[str, object]]]:
    with db_conn() as conn:
        comparison: list[dict[str, object]] = []
        for row in fetch_managed_account_rows(conn):
            summary = build_account_summary(conn, row)
            latest_backtest = fetch_latest_backtest_metrics(conn, str(row["name"]))
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
            payload["latestBacktest"] = fetch_latest_backtest_summary(conn, resolved_account_name)
        return payload

    with db_conn() as conn:
        account = fetch_account_row(conn, account_name)
        summary = build_account_summary(conn, account)

        snapshots = fetch_account_snapshot_rows(conn, int(account["id"]), limit=100)

        trades = fetch_account_trades(conn, int(account["id"]))
        latest_backtest = fetch_latest_backtest_summary(conn, account_name)

        return {
            "account": summary,
            "latestBacktest": latest_backtest,
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
        update_account_params(
            conn,
            int(account["id"]),
            strategy=body.strategy,
            risk_policy=body.riskPolicy,
            descriptive_name=body.descriptiveName,
            stop_loss_pct=body.stopLossPct,
            take_profit_pct=body.takeProfitPct,
            instrument_mode=body.instrumentMode,
            goal_min_return_pct=body.goalMinReturnPct,
            goal_max_return_pct=body.goalMaxReturnPct,
            goal_period=body.goalPeriod,
            learning_enabled=body.learningEnabled,
            option_strike_offset_pct=body.optionStrikeOffsetPct,
            option_min_dte=body.optionMinDte,
            option_max_dte=body.optionMaxDte,
            option_type=body.optionType,
            target_delta_min=body.targetDeltaMin,
            target_delta_max=body.targetDeltaMax,
            max_premium_per_trade=body.maxPremiumPerTrade,
            max_contracts_per_trade=body.maxContractsPerTrade,
            iv_rank_min=body.ivRankMin,
            iv_rank_max=body.ivRankMax,
            roll_dte_threshold=body.rollDteThreshold,
            profit_take_pct=body.profitTakePct,
            max_loss_pct=body.maxLossPct,
        )
    return {"status": "ok"}

