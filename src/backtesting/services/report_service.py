"""Report service: full backtest report assembly.

This service module owns:

- ``fetch_backtest_report_data``: assembles a ``BacktestFullReport`` from
  persisted run, snapshot, and trade rows, including benchmark return and alpha
  calculation.
- Thin wrappers around ``report_repository`` reads for latest-run and
  recent-run lookups.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import date

from backtesting.domain.metrics import (
    benchmark_return_pct,
    max_drawdown_pct,
    summarize_backtest_performance,
)
from backtesting.report_models import (
    BacktestFullReport,
    BacktestReportSnapshot,
    BacktestReportSummary,
    BacktestReportTrade,
    parse_warnings,
)
from backtesting.repositories.report_repository import (
    fetch_backtest_report_run,
    fetch_backtest_report_snapshots,
    fetch_backtest_report_trades,
    fetch_latest_backtest_run_for_account as _repo_fetch_latest_backtest_run_for_account,
    fetch_latest_backtest_run_id_for_account as _repo_fetch_latest_backtest_run_id_for_account,
    fetch_recent_backtest_runs as _repo_fetch_recent_backtest_runs,
)
from backtesting.services.backtest_data_service import fetch_benchmark_close
from common.coercion import row_expect_float, row_expect_int, row_expect_str, row_float, row_str
from trading.domain.exceptions import NotFoundError
from trading.services.market_data import MarketDataProvider

logger = logging.getLogger(__name__)


def _benchmark_and_alpha(
    run,
    total_return_pct: float,
    provider: MarketDataProvider | None,
) -> tuple[float | None, float | None]:
    """Benchmark return and alpha for *run*, or ``(None, None)``.

    The benchmark is the only part of a report that needs market data, so the
    provider is what asks for it. Callers that want just the summary omit it
    rather than injecting a provider they have no use for — the account list
    reads one summary per row, and computing a benchmark series for each would
    be a provider round trip per account.
    """
    if provider is None:
        return None, None

    try:
        benchmark_series = fetch_benchmark_close(
            row_expect_str(run, "benchmark_ticker"),
            date.fromisoformat(row_expect_str(run, "start_date")),
            date.fromisoformat(row_expect_str(run, "end_date")),
            provider=provider,
        )
    except Exception as exc:
        # A benchmark with no history over the run's window is a data gap, not a
        # reason to fail the whole report.
        logger.warning("Failed to compute benchmark return for backtest run: %s", exc, exc_info=True)
        return None, None

    benchmark_ret = benchmark_return_pct(benchmark_series, row_expect_float(run, "initial_cash"))
    if benchmark_ret is None:
        return None, None
    return benchmark_ret, total_return_pct - benchmark_ret


def fetch_backtest_report_data(
    conn,
    *,
    run_id: int,
    provider: MarketDataProvider | None = None,
) -> BacktestFullReport:
    run = fetch_backtest_report_run(conn, run_id)
    if run is None:
        raise NotFoundError(f"Backtest run id {run_id} not found")

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
        warnings=parse_warnings(run["warnings"]),
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

    benchmark_ret, alpha_pct = _benchmark_and_alpha(run, summary.total_return_pct, provider)

    return BacktestFullReport(
        summary=summary,
        benchmark_ticker=row_expect_str(run, "benchmark_ticker"),
        notes=run["notes"],
        snapshots=report_snapshots,
        trades=report_trades,
        benchmark_return_pct=benchmark_ret,
        alpha_pct=alpha_pct,
    )


def fetch_latest_backtest_run_id_for_account(conn, *, account_name: str) -> int | None:
    return _repo_fetch_latest_backtest_run_id_for_account(conn, account_name=account_name)


def _build_backtest_run_dict(row: Mapping[str, object]) -> dict[str, object]:
    """Convert a backtest run row to a serialisable dict with raw (un-substituted) values."""
    return {
        "runId": row_expect_int(row, "id"),
        "runName": row["run_name"],
        "accountName": row_expect_str(row, "account_name"),
        "strategy": row_expect_str(row, "strategy"),
        "startDate": row["start_date"],
        "endDate": row["end_date"],
        "createdAt": row["created_at"],
        "slippageBps": row_expect_float(row, "slippage_bps"),
        "feePerTrade": row_expect_float(row, "fee_per_trade"),
        "tickersFile": row["tickers_file"],
    }


def fetch_latest_backtest_run_for_account(conn, *, account_name: str) -> dict[str, object] | None:
    row = _repo_fetch_latest_backtest_run_for_account(conn, account_name=account_name)
    if row is None:
        return None
    return _build_backtest_run_dict(row)


def fetch_recent_backtest_runs(conn, *, limit: int) -> list[dict[str, object]]:
    return [_build_backtest_run_dict(row) for row in _repo_fetch_recent_backtest_runs(conn, limit=limit)]


def fetch_backtest_report_summary(conn, run_id: int) -> BacktestReportSummary:
    """The run's summary only — no benchmark, so no market-data provider needed."""
    return fetch_backtest_report_data(conn, run_id=run_id).summary
