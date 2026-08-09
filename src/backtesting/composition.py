from __future__ import annotations

import sqlite3

from backtesting.models import (
    BacktestBatchConfig,
    BacktestConfig,
    BacktestResult,
)
from backtesting.models.report import BacktestFullReport, BacktestLeaderboardEntry
from backtesting.services import (
    fetch_backtest_leaderboard_entries,
    fetch_backtest_report_data,
    fetch_bar_history,
    fetch_benchmark_close,
    run_backtest as run_backtest_impl,
)
from infrastructure.market_data.factory import build_provider
from trading.domain.strategies.resolution import resolve_strategy
from trading.services.market_data import build_feature_provider


def _run_backtest(conn: sqlite3.Connection, cfg: BacktestConfig, *, persist: bool) -> BacktestResult:
    # Composition seam: build the market-data + feature providers once for the
    # run and inject them down the data path (no global access inside services).
    provider = build_provider()
    feature_provider = build_feature_provider(market_data_provider=provider)
    return run_backtest_impl(
        conn,
        cfg,
        fetch_bar_history_fn=lambda tickers, start_date, end_date: fetch_bar_history(
            tickers, start_date, end_date, provider=provider
        ),
        fetch_benchmark_close_fn=lambda benchmark_ticker, start_date, end_date: fetch_benchmark_close(
            benchmark_ticker, start_date, end_date, provider=provider
        ),
        persist=persist,
        feature_provider=feature_provider,
    )


def run_backtest(conn: sqlite3.Connection, cfg: BacktestConfig) -> BacktestResult:
    return _run_backtest(conn, cfg, persist=True)


def run_backtest_metrics_only(conn: sqlite3.Connection, cfg: BacktestConfig) -> BacktestResult:
    """Run a simulation and return its metrics without persisting any run, trade, or
    snapshot rows. Lets the walk-forward optimizer evaluate grid candidates on training
    windows without polluting stored backtest evidence."""
    return _run_backtest(conn, cfg, persist=False)


def backtest_report_full(conn: sqlite3.Connection, run_id: int) -> BacktestFullReport:
    """The full report, benchmark and alpha included.

    Takes no provider: the benchmark return is read from the run row, frozen
    there when the run executed, so reading a report touches no market data.
    """
    return fetch_backtest_report_data(conn, run_id=run_id)


def _validated_strategy_filter(strategy: str | None) -> str | None:
    if strategy is None:
        return None
    strategy_name = strategy.strip()
    if not strategy_name:
        return None
    resolve_strategy(strategy_name)
    return strategy_name


def backtest_leaderboard_entries(
    conn: sqlite3.Connection,
    *,
    limit: int = 10,
    account_name: str | None = None,
    strategy: str | None = None,
) -> list[BacktestLeaderboardEntry]:
    return [
        entry
        for entry, _starting_equity in fetch_backtest_leaderboard_entries(
            conn,
            limit=limit,
            account_name=account_name,
            strategy=_validated_strategy_filter(strategy),
        )
    ]


def run_backtest_batch(conn: sqlite3.Connection, cfg: BacktestBatchConfig) -> list[BacktestResult]:
    account_names = [name.strip() for name in cfg.account_names if name.strip()]
    if not account_names:
        raise ValueError("At least one account name is required.")

    results: list[BacktestResult] = []
    for idx, account_name in enumerate(account_names, start=1):
        run_name = None
        if cfg.run_name_prefix:
            run_name = f"{cfg.run_name_prefix}_{idx:02d}_{account_name}"

        result = run_backtest(
            conn,
            BacktestConfig(
                account_name=account_name,
                tickers_file=cfg.tickers_file,
                universe_history_dir=cfg.universe_history_dir,
                start=cfg.start,
                end=cfg.end,
                lookback_months=cfg.lookback_months,
                slippage_bps=cfg.slippage_bps,
                fee_per_trade=cfg.fee_per_trade,
                run_name=run_name,
                allow_approximate_leaps=cfg.allow_approximate_leaps,
            ),
        )
        results.append(result)

    results.sort(key=lambda item: item.total_return_pct, reverse=True)
    return results
