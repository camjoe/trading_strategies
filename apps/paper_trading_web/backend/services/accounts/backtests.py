from __future__ import annotations

import sqlite3

from backtesting.models.report import BacktestRunSummary
from backtesting.services.report_service import (
    fetch_latest_run_for_account,
    fetch_latest_run_id_for_account,
    fetch_recent_runs,
    fetch_report_summary,
)


def _run_payload(run: BacktestRunSummary) -> dict[str, object]:
    return {
        "runId": run.run_id,
        "runName": run.run_name,
        "accountName": run.account_name,
        "strategy": run.strategy,
        "startDate": run.start_date,
        "endDate": run.end_date,
        "createdAt": run.created_at,
        "slippageBps": run.slippage_bps,
        "feePerTrade": run.fee_per_trade,
        "tickersFile": run.tickers_file,
    }


def fetch_latest_backtest_summary(conn: sqlite3.Connection, account_name: str) -> dict[str, object] | None:
    run = fetch_latest_run_for_account(conn, account_name=account_name)
    return None if run is None else _run_payload(run)


def fetch_recent_backtest_run_summaries(conn: sqlite3.Connection, *, limit: int) -> list[dict[str, object]]:
    return [_run_payload(run) for run in fetch_recent_runs(conn, limit=limit)]


def fetch_latest_backtest_metrics(conn: sqlite3.Connection, account_name: str) -> dict[str, object] | None:
    latest_run_id = fetch_latest_run_id_for_account(conn, account_name=account_name)
    if latest_run_id is None:
        return None

    try:
        report = fetch_report_summary(conn, int(latest_run_id))
    except ValueError:
        return None
    return {
        "runId": report.run_id,
        "endDate": report.end_date,
        "totalReturnPct": report.total_return_pct,
        "maxDrawdownPct": report.max_drawdown_pct,
        "sharpeRatio": report.sharpe_ratio,
        "sortinoRatio": report.sortino_ratio,
        "calmarRatio": report.calmar_ratio,
        "winRatePct": report.win_rate_pct,
        "profitFactor": report.profit_factor,
        "avgTradeReturnPct": report.avg_trade_return_pct,
    }
