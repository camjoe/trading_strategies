"""Operator-facing reads over persisted backtest runs.

One run's full report or summary, the run listings behind a history view, and the
leaderboard that ranks runs against each other. All of it comes from the same three
tables and the same performance math, and returns the shapes in `models/report.py`.

Needs no market data: a run's benchmark return is read from its row, frozen there
when the run executed.

Everything here returns typed models. Transport shaping (camelCase keys, display
names) belongs to the surface that serves it, not to this package.
"""

from __future__ import annotations

from collections.abc import Mapping

from backtesting.domain.metrics import (
    equity_curve_from_rows,
    max_drawdown_pct,
    summarize_backtest_performance,
)
from backtesting.models.report import (
    BacktestFullReport,
    BacktestLeaderboardEntry,
    BacktestReportSnapshot,
    BacktestReportSummary,
    BacktestReportTrade,
    BacktestRunSummary,
    parse_warnings,
)
from backtesting.repositories.runs import (
    fetch_leaderboard_rows,
    fetch_run,
    fetch_runs,
    fetch_snapshots,
    fetch_trades,
)
from common.coercion import row_expect_float, row_expect_int, row_expect_str, row_float, row_str
from trading.domain.exceptions import NotFoundError
from trading.domain.metrics.returns import total_return_pct
from trading.domain.strategies.resolution import validate_strategy_name


def _require_run_parts(
    conn,
    run_id: int,
) -> tuple[Mapping[str, object], list[dict[str, object]], list[dict[str, object]]]:
    """A run's header, snapshots, and trades — or the error a missing one warrants."""
    run = fetch_run(conn, run_id)
    if run is None:
        raise NotFoundError(f"Backtest run id {run_id} not found")

    snapshots = fetch_snapshots(conn, run_id)
    trades = fetch_trades(conn, run_id)

    if not snapshots:
        raise ValueError(f"No snapshots found for backtest run {run_id}")

    return run, snapshots, trades


def _build_summary(
    run: Mapping[str, object],
    snapshots: list[dict[str, object]],
    trades: list[dict[str, object]],
) -> BacktestReportSummary:
    first_equity = row_expect_float(snapshots[0], "equity")
    last_equity = row_expect_float(snapshots[-1], "equity")

    curve = equity_curve_from_rows(snapshots)
    max_drawdown = max_drawdown_pct(curve)
    performance = summarize_backtest_performance(curve, trades)

    return BacktestReportSummary(
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
        total_return_pct=total_return_pct(first_equity=first_equity, last_equity=last_equity),
        max_drawdown_pct=max_drawdown,
        sharpe_ratio=performance.sharpe_ratio,
        sortino_ratio=performance.sortino_ratio,
        calmar_ratio=performance.calmar_ratio,
        win_rate_pct=performance.win_rate_pct,
        profit_factor=performance.profit_factor,
        avg_trade_return_pct=performance.avg_trade_return_pct,
    )


def fetch_report_summary(conn, run_id: int) -> BacktestReportSummary:
    """The run's summary alone.

    Reads the same rows the full report does, but skips the per-snapshot and
    per-trade model lists a summary caller would only discard.
    """
    return _build_summary(*_require_run_parts(conn, run_id))


def fetch_report(conn, *, run_id: int) -> BacktestFullReport:
    run, snapshots, trades = _require_run_parts(conn, run_id)
    summary = _build_summary(run, snapshots, trades)

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

    # Frozen when the run executed. Null when the benchmark window held fewer than
    # two usable closes, so there was no return to compute.
    benchmark_ret = row_float(run, "benchmark_return_pct")
    alpha_pct = None if benchmark_ret is None else summary.total_return_pct - benchmark_ret

    return BacktestFullReport(
        summary=summary,
        benchmark_ticker=row_expect_str(run, "benchmark_ticker"),
        notes=run["notes"],
        snapshots=report_snapshots,
        trades=report_trades,
        benchmark_return_pct=benchmark_ret,
        alpha_pct=alpha_pct,
    )


def fetch_latest_run_id_for_account(conn, *, account_name: str) -> int | None:
    rows = fetch_runs(conn, limit=1, account_name=account_name)
    return row_expect_int(rows[0], "id") if rows else None


def fetch_latest_run_for_account(conn, *, account_name: str) -> BacktestRunSummary | None:
    rows = fetch_runs(conn, limit=1, account_name=account_name)
    return BacktestRunSummary.from_mapping(rows[0]) if rows else None


def fetch_recent_runs(conn, *, limit: int) -> list[BacktestRunSummary]:
    return [BacktestRunSummary.from_mapping(row) for row in fetch_runs(conn, limit=limit)]


def _validated_strategy_filter(strategy: str | None) -> str | None:
    """The filter's canonical strategy key, or None for "no filter".

    Runs store a strategies FK, so the board matches on the canonical key: an
    alias or display name has to resolve to it here or it would match no row and
    return an empty board, which reads the same as "this strategy has no runs".
    An unknown name raises instead.
    """
    if strategy is None:
        return None
    strategy_name = strategy.strip()
    if not strategy_name:
        return None
    return validate_strategy_name(strategy_name)


def fetch_leaderboard(
    conn,
    *,
    limit: int = 10,
    account_name: str | None = None,
    strategy: str | None = None,
) -> list[BacktestLeaderboardEntry]:
    """Persisted runs ranked by total return, best first."""
    if limit <= 0:
        raise ValueError("limit must be > 0")

    rows = fetch_leaderboard_rows(
        conn,
        limit=limit,
        account_name=account_name,
        strategy=_validated_strategy_filter(strategy),
    )

    return [_leaderboard_entry(conn, row) for row in rows]


def _leaderboard_entry(conn, row) -> BacktestLeaderboardEntry:
    """One ranked run, with the metrics that need its full curve and trade list."""
    run_id = row_expect_int(row, "run_id")
    start_equity = row_expect_float(row, "starting_equity")
    end_equity = row_expect_float(row, "ending_equity")

    curve = equity_curve_from_rows(fetch_snapshots(conn, run_id))
    trades = fetch_trades(conn, run_id)
    performance = summarize_backtest_performance(curve, trades)

    total_return = total_return_pct(first_equity=start_equity, last_equity=end_equity)
    # Frozen when the run executed; null when its benchmark window was too short.
    benchmark_ret = row_float(row, "benchmark_return_pct")

    return BacktestLeaderboardEntry(
        run_id=run_id,
        run_name=row_str(row, "run_name"),
        account_name=row_expect_str(row, "account_name"),
        strategy=row_expect_str(row, "strategy"),
        start_date=row_expect_str(row, "start_date"),
        end_date=row_expect_str(row, "end_date"),
        created_at=row_expect_str(row, "created_at"),
        trade_count=len(trades),
        ending_equity=end_equity,
        total_return_pct=total_return,
        max_drawdown_pct=max_drawdown_pct(curve),
        benchmark_return_pct=benchmark_ret,
        alpha_pct=None if benchmark_ret is None else total_return - benchmark_ret,
        sharpe_ratio=performance.sharpe_ratio,
        sortino_ratio=performance.sortino_ratio,
        calmar_ratio=performance.calmar_ratio,
        win_rate_pct=performance.win_rate_pct,
        profit_factor=performance.profit_factor,
        avg_trade_return_pct=performance.avg_trade_return_pct,
    )
