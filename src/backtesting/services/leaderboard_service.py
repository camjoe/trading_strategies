from __future__ import annotations

from backtesting.domain.metrics import equity_curve_from_rows, max_drawdown_pct, summarize_backtest_performance
from backtesting.models.report import BacktestLeaderboardEntry
from backtesting.repositories.runs import (
    fetch_leaderboard_rows,
    fetch_snapshots,
    fetch_trades,
)
from common.coercion import row_expect_int, row_expect_str, row_float, row_str
from trading.domain.strategies.resolution import resolve_strategy


def _validated_strategy_filter(strategy: str | None) -> str | None:
    """Resolve a strategy filter to its canonical name, or None for "no filter".

    Resolving rejects an unknown name up front rather than silently returning an
    empty leaderboard, which reads the same as "this strategy has no runs".
    """
    if strategy is None:
        return None
    strategy_name = strategy.strip()
    if not strategy_name:
        return None
    resolve_strategy(strategy_name)
    return strategy_name


def fetch_backtest_leaderboard_entries(
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

    entries: list[BacktestLeaderboardEntry] = []
    for row in rows:
        start_equity = row_float(row, "starting_equity")
        end_equity = row_float(row, "ending_equity")
        if start_equity is None or end_equity is None or start_equity <= 0:
            continue

        run_id = row_expect_int(row, "run_id")
        curve = equity_curve_from_rows(fetch_snapshots(conn, run_id))
        max_drawdown = max_drawdown_pct(curve)
        performance = summarize_backtest_performance(curve, fetch_trades(conn, run_id))

        total_return_pct = ((end_equity / start_equity) - 1.0) * 100.0

        # Frozen when the run executed; null when its benchmark window was too short.
        benchmark_ret = row_float(row, "benchmark_return_pct")
        alpha_pct = None if benchmark_ret is None else total_return_pct - benchmark_ret

        entries.append(
            BacktestLeaderboardEntry(
                run_id=row_expect_int(row, "run_id"),
                run_name=row_str(row, "run_name"),
                account_name=row_expect_str(row, "account_name"),
                strategy=row_expect_str(row, "strategy"),
                start_date=row_expect_str(row, "start_date"),
                end_date=row_expect_str(row, "end_date"),
                created_at=row_expect_str(row, "created_at"),
                trade_count=row_expect_int(row, "trade_count"),
                ending_equity=float(end_equity),
                total_return_pct=float(total_return_pct),
                max_drawdown_pct=float(max_drawdown),
                benchmark_return_pct=benchmark_ret,
                alpha_pct=alpha_pct,
                sharpe_ratio=performance.sharpe_ratio,
                sortino_ratio=performance.sortino_ratio,
                calmar_ratio=performance.calmar_ratio,
                win_rate_pct=performance.win_rate_pct,
                profit_factor=performance.profit_factor,
                avg_trade_return_pct=performance.avg_trade_return_pct,
            )
        )

    entries.sort(key=lambda entry: entry.total_return_pct, reverse=True)
    return entries
