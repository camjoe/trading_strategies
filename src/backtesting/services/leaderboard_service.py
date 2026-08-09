from __future__ import annotations

from backtesting.domain.metrics import equity_curve_from_rows, max_drawdown_pct, summarize_backtest_performance
from backtesting.models.report import BacktestLeaderboardEntry
from backtesting.repositories.runs import (
    fetch_leaderboard_rows,
    fetch_snapshots,
    fetch_trades,
)
from common.coercion import row_expect_float, row_expect_int, row_expect_str, row_float, row_str
from trading.domain.strategies.resolution import resolve_strategy


def _validated_strategy_filter(strategy: str | None) -> str | None:
    """The filter's canonical strategy name, or None for "no filter".

    Resolving rejects an unknown name rather than returning an empty board, which
    reads the same as "this strategy has no runs".
    """
    if strategy is None:
        return None
    strategy_name = strategy.strip()
    if not strategy_name:
        return None
    resolve_strategy(strategy_name)
    return strategy_name


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

    return [_entry(conn, row) for row in rows]


def _entry(conn, row) -> BacktestLeaderboardEntry:
    """One ranked run, with the metrics that need its full curve and trade list."""
    run_id = row_expect_int(row, "run_id")
    start_equity = row_expect_float(row, "starting_equity")
    end_equity = row_expect_float(row, "ending_equity")

    curve = equity_curve_from_rows(fetch_snapshots(conn, run_id))
    trades = fetch_trades(conn, run_id)
    performance = summarize_backtest_performance(curve, trades)

    total_return_pct = ((end_equity / start_equity) - 1.0) * 100.0
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
        total_return_pct=total_return_pct,
        max_drawdown_pct=max_drawdown_pct(curve),
        benchmark_return_pct=benchmark_ret,
        alpha_pct=None if benchmark_ret is None else total_return_pct - benchmark_ret,
        sharpe_ratio=performance.sharpe_ratio,
        sortino_ratio=performance.sortino_ratio,
        calmar_ratio=performance.calmar_ratio,
        win_rate_pct=performance.win_rate_pct,
        profit_factor=performance.profit_factor,
        avg_trade_return_pct=performance.avg_trade_return_pct,
    )
