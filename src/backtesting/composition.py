from __future__ import annotations

import sqlite3

from backtesting.models import (
    BacktestBatchConfig,
    BacktestConfig,
    BacktestResult,
)
from backtesting.services.run_inputs import fetch_bar_history, fetch_benchmark_close
from backtesting.services.simulation import run_backtest as run_backtest_impl
from trading.services.market_data.factory import build_feature_provider
from trading.services.market_data.protocols import MarketDataProvider


def _run_backtest(
    conn: sqlite3.Connection,
    cfg: BacktestConfig,
    *,
    provider: MarketDataProvider,
    persist: bool,
) -> BacktestResult:
    # Binds one caller-supplied provider into the run's data path, so no service
    # below reaches for a provider itself.
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


def run_backtest(
    conn: sqlite3.Connection,
    cfg: BacktestConfig,
    *,
    provider: MarketDataProvider,
) -> BacktestResult:
    """Run one backtest against *provider* and persist it.

    The provider is supplied, never built here: the application entrypoint builds
    one per invocation. A provider carries per-instance call guards (the yfinance
    adapter's rate limiter caps cumulative calls for its own lifetime), so
    building one per run would reset those guards on every run — and an optimizer
    sweep runs one backtest per candidate per window.
    """
    return _run_backtest(conn, cfg, provider=provider, persist=True)


def run_backtest_metrics_only(
    conn: sqlite3.Connection,
    cfg: BacktestConfig,
    *,
    provider: MarketDataProvider,
) -> BacktestResult:
    """Run a simulation and return its metrics without persisting any run, trade, or
    snapshot rows. Lets the walk-forward optimizer evaluate grid candidates on training
    windows without polluting stored backtest evidence."""
    return _run_backtest(conn, cfg, provider=provider, persist=False)


def run_backtest_batch(
    conn: sqlite3.Connection,
    cfg: BacktestBatchConfig,
    *,
    provider: MarketDataProvider,
) -> list[BacktestResult]:
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
            provider=provider,
        )
        results.append(result)

    results.sort(key=lambda item: item.total_return_pct, reverse=True)
    return results
