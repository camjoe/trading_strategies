from __future__ import annotations

from datetime import date
from typing import Callable

import pandas as pd

from trading.backtesting.domain.metrics import benchmark_return_pct, max_drawdown_pct
from trading.backtesting.repositories.leaderboard_repository import fetch_equity_rows, fetch_leaderboard_rows
from trading.backtesting.trading_bridge import row_expect_float, row_expect_int, row_expect_str, row_float, row_str
from trading.backtesting.report_models import BacktestLeaderboardEntry

BenchmarkFetcher = Callable[[str, date, date], pd.Series | pd.DataFrame]


def fetch_backtest_leaderboard_entries(
    conn,
    *,
    limit: int,
    account_name: str | None,
    strategy: str | None,
    fetch_benchmark_close_fn: BenchmarkFetcher,
) -> list[tuple[BacktestLeaderboardEntry, float]]:
    if limit <= 0:
        raise ValueError("limit must be > 0")

    rows = fetch_leaderboard_rows(
        conn,
        limit=limit,
        account_name=account_name,
        strategy=strategy,
    )

    entries: list[tuple[BacktestLeaderboardEntry, float]] = []
    for row in rows:
        start_equity = row_float(row, "starting_equity")
        end_equity = row_float(row, "ending_equity")
        if start_equity is None or end_equity is None or start_equity <= 0:
            continue

        equity_rows = fetch_equity_rows(conn, row_expect_int(row, "run_id"))
        curve = [row_float(item, "equity") for item in equity_rows]
        max_drawdown = max_drawdown_pct([value for value in curve if value is not None])

        total_return_pct = ((end_equity / start_equity) - 1.0) * 100.0

        benchmark_ret: float | None = None
        alpha_pct: float | None = None
        try:
            benchmark_series = fetch_benchmark_close_fn(
                row_expect_str(row, "benchmark_ticker"),
                date.fromisoformat(row_expect_str(row, "start_date")),
                date.fromisoformat(row_expect_str(row, "end_date")),
            )
            benchmark_ret = benchmark_return_pct(
                benchmark_series,
                row_expect_float(row, "initial_cash"),
            )
            if benchmark_ret is not None:
                alpha_pct = total_return_pct - benchmark_ret
        except Exception:
            benchmark_ret = None
            alpha_pct = None

        entry = BacktestLeaderboardEntry(
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
        )
        entries.append((entry, float(start_equity)))

    entries.sort(
        key=lambda item: item[0].total_return_pct,
        reverse=True,
    )
    return entries
