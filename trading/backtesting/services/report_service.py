"""Report service: full backtest report assembly and re-export facade.

This service module owns:

- ``fetch_backtest_report_data``: assembles a ``BacktestFullReport`` from
  persisted run, snapshot, and trade rows, including benchmark return and alpha
  calculation.
- Thin wrappers around ``report_repository`` reads for latest-run and
  recent-run lookups.

Re-exports:

- ``resolve_signal`` from ``trading.backtesting.domain.strategy_signals`` —
  callers that need signal dispatch should import from here rather than the
  domain module directly, keeping the service-layer boundary intact.
"""
from __future__ import annotations

from datetime import date
from typing import Callable

import pandas as pd

# Re-exported so callers never reach into trading.backtesting.domain directly.
from trading.backtesting.domain.strategy_signals import resolve_signal  # noqa: F401

from trading.backtesting.domain.metrics import (
    benchmark_return_pct,
    max_drawdown_pct,
    summarize_backtest_performance,
)
from trading.backtesting.repositories.report_repository import (
    fetch_backtest_report_run,
    fetch_backtest_report_snapshots,
    fetch_backtest_report_trades,
    fetch_latest_backtest_run_for_account as _repo_fetch_latest_backtest_run_for_account,
    fetch_latest_backtest_run_id_for_account as _repo_fetch_latest_backtest_run_id_for_account,
    fetch_recent_backtest_runs as _repo_fetch_recent_backtest_runs,
)
from common.coercion import row_expect_float, row_expect_int, row_expect_str, row_float, row_str
from trading.backtesting.report_models import (
    BacktestFullReport,
    BacktestReportSnapshot,
    BacktestReportSummary,
    BacktestReportTrade,
)

BenchmarkFetcher = Callable[[str, date, date], pd.Series | pd.DataFrame]


def fetch_backtest_report_data(
    conn,
    *,
    run_id: int,
    fetch_benchmark_close_fn: BenchmarkFetcher,
) -> BacktestFullReport:
    run = fetch_backtest_report_run(conn, run_id)
    if run is None:
        raise ValueError(f"Backtest run id {run_id} not found")

    snapshots = fetch_backtest_report_snapshots(conn, run_id)
    trades = fetch_backtest_report_trades(conn, run_id)

    if not snapshots:
        raise ValueError(f"No snapshots found for backtest run {run_id}")

    first_equity = row_expect_float(snapshots[0], "equity")
    last_equity = row_expect_float(snapshots[-1], "equity")

    equity_curve = [row_float(item, "equity") for item in snapshots]
    max_drawdown = max_drawdown_pct([value for value in equity_curve if value is not None])
    performance = summarize_backtest_performance(
        [value for value in equity_curve if value is not None],
        trades,
    )

    summary = BacktestReportSummary(
        run_id=row_expect_int(run, "id"),
        run_name=row_str(run, "run_name"),
        account_name=row_expect_str(run, "account_name"),
        strategy=row_expect_str(run, "strategy"),
        start_date=row_expect_str(run, "start_date"),
        end_date=row_expect_str(run, "end_date"),
        created_at=row_expect_str(run, "created_at"),
        slippage_bps=row_expect_float(run, "slippage_bps"),
        fee_per_trade=row_expect_float(run, "fee_per_trade"),
        tickers_file=row_expect_str(run, "tickers_file"),
        warnings=run["warnings"],
        trade_count=len(trades),
        starting_equity=first_equity,
        ending_equity=last_equity,
        total_return_pct=((last_equity / first_equity) - 1.0) * 100.0,
        max_drawdown_pct=max_drawdown,
        sharpe_ratio=performance.sharpe_ratio,
        sortino_ratio=performance.sortino_ratio,
        calmar_ratio=performance.calmar_ratio,
        win_rate_pct=performance.win_rate_pct,
        profit_factor=performance.profit_factor,
        avg_trade_return_pct=performance.avg_trade_return_pct,
    )

    report_snapshots = [
        BacktestReportSnapshot(
            snapshot_time=row_expect_str(item, "snapshot_time"),
            cash=row_expect_float(item, "cash"),
            market_value=row_expect_float(item, "market_value"),
            equity=row_expect_float(item, "equity"),
            realized_pnl=row_expect_float(item, "realized_pnl"),
            unrealized_pnl=row_expect_float(item, "unrealized_pnl"),
        )
        for item in snapshots
    ]
    report_trades = [
        BacktestReportTrade(
            trade_time=row_expect_str(item, "trade_time"),
            ticker=row_expect_str(item, "ticker"),
            side=row_expect_str(item, "side"),
            qty=row_expect_float(item, "qty"),
            price=row_expect_float(item, "price"),
            fee=row_expect_float(item, "fee"),
        )
        for item in trades
    ]

    benchmark_ret: float | None = None
    alpha_pct: float | None = None
    try:
        benchmark_series = fetch_benchmark_close_fn(
            row_expect_str(run, "benchmark_ticker"),
            date.fromisoformat(row_expect_str(run, "start_date")),
            date.fromisoformat(row_expect_str(run, "end_date")),
        )
        benchmark_ret = benchmark_return_pct(benchmark_series, row_expect_float(run, "initial_cash"))
        if benchmark_ret is not None:
            alpha_pct = summary.total_return_pct - benchmark_ret
    except Exception:
        benchmark_ret = None
        alpha_pct = None

    return BacktestFullReport(
        summary=summary,
        benchmark_ticker=row_expect_str(run, "benchmark_ticker"),
        notes=run["notes"],
        snapshots=report_snapshots,
        trades=report_trades,
        benchmark_return_pct=benchmark_ret,
        alpha_pct=alpha_pct,
    )


def fetch_latest_backtest_run_for_account(conn, *, account_name: str) -> object:
    return _repo_fetch_latest_backtest_run_for_account(conn, account_name=account_name)


def fetch_latest_backtest_run_id_for_account(conn, *, account_name: str) -> int | None:
    return _repo_fetch_latest_backtest_run_id_for_account(conn, account_name=account_name)


def fetch_recent_backtest_runs(conn, *, limit: int) -> list[object]:
    return _repo_fetch_recent_backtest_runs(conn, limit=limit)


def fetch_backtest_report_summary(conn, run_id: int) -> BacktestReportSummary:
    from trading.backtesting.backtest import backtest_report_summary  # deferred to avoid circular import
    return backtest_report_summary(conn, run_id)
