from __future__ import annotations

import pandas as pd

from trading.models import AccountConfig
from trading.services.accounts import create_account
from trading.backtesting.backtest import BacktestConfig, WalkForwardConfig
from trading.backtesting.models import BacktestResult
from trading.backtesting.report_models import BacktestLeaderboardEntry


def make_fake_close_history(tickers: list[str]) -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=40, freq="B")
    data: dict[str, list[float]] = {}
    for i, ticker in enumerate(tickers):
        base = 100.0 + (i * 5.0)
        values = [base + (j * 0.8) for j in range(30)] + [base + 24.0 - ((j - 30) * 0.9) for j in range(30, 40)]
        data[ticker] = values
    return pd.DataFrame(data, index=idx)


def install_backtest_market_data(
    monkeypatch,
    backtest_module,
    *,
    tickers: list[str],
    benchmark_values: list[float],
) -> None:
    monkeypatch.setattr(backtest_module, "load_tickers_from_file", lambda _path: tickers)
    monkeypatch.setattr(
        backtest_module,
        "fetch_close_history",
        lambda _tickers, _start, _end: make_fake_close_history(_tickers),
    )
    monkeypatch.setattr(
        backtest_module,
        "fetch_benchmark_close",
        lambda _ticker, _start, _end: pd.Series(
            benchmark_values,
            index=pd.date_range("2026-01-01", periods=len(benchmark_values), freq="B"),
        ),
    )


def create_backtest_account(
    conn,
    name: str,
    strategy: str = "trend_v1",
    initial_cash: float = 10000.0,
    benchmark: str = "SPY",
    **kwargs,
) -> None:
    create_account(conn, name, strategy, initial_cash, benchmark, config=AccountConfig(**kwargs) if kwargs else None)


def make_backtest_config(
    account_name: str,
    *,
    start: str = "2026-01-01",
    end: str = "2026-03-01",
    universe_history_dir: str | None = None,
    slippage_bps: float = 5.0,
    fee_per_trade: float = 0.0,
    run_name: str | None = None,
    allow_approximate_leaps: bool = False,
) -> BacktestConfig:
    return BacktestConfig(
        account_name=account_name,
        tickers_file="trading/config/trade_universe.txt",
        universe_history_dir=universe_history_dir,
        start=start,
        end=end,
        lookback_months=None,
        slippage_bps=slippage_bps,
        fee_per_trade=fee_per_trade,
        run_name=run_name,
        allow_approximate_leaps=allow_approximate_leaps,
    )


def make_walk_forward_config(
    account_name: str,
    *,
    start: str,
    end: str,
    test_months: int,
    step_months: int,
    slippage_bps: float = 5.0,
    fee_per_trade: float = 0.0,
    run_name_prefix: str | None = None,
    allow_approximate_leaps: bool = False,
) -> WalkForwardConfig:
    return WalkForwardConfig(
        account_name=account_name,
        tickers_file="trading/config/trade_universe.txt",
        universe_history_dir=None,
        start=start,
        end=end,
        lookback_months=None,
        test_months=test_months,
        step_months=step_months,
        slippage_bps=slippage_bps,
        fee_per_trade=fee_per_trade,
        run_name_prefix=run_name_prefix,
        allow_approximate_leaps=allow_approximate_leaps,
    )


def make_backtest_result(
    account_name: str,
    *,
    run_id: int = 1,
    total_return_pct: float = 0.0,
    ending_equity: float = 10_000.0,
    trade_count: int = 1,
    start_date: str = "2026-01-01",
    end_date: str = "2026-02-01",
    tickers: list[str] | None = None,
    benchmark_return_pct: float | None = 0.5,
    alpha_pct: float | None = None,
    max_drawdown_pct: float = -1.0,
    sharpe_ratio: float | None = None,
    sortino_ratio: float | None = None,
    calmar_ratio: float | None = None,
    win_rate_pct: float | None = None,
    profit_factor: float | None = None,
    avg_trade_return_pct: float | None = None,
    warnings: list[str] | None = None,
) -> BacktestResult:
    if alpha_pct is None and benchmark_return_pct is not None:
        alpha_pct = total_return_pct - benchmark_return_pct
    return BacktestResult(
        run_id=run_id,
        account_name=account_name,
        start_date=start_date,
        end_date=end_date,
        tickers=tickers or ["AAPL"],
        trade_count=trade_count,
        ending_equity=ending_equity,
        total_return_pct=total_return_pct,
        benchmark_return_pct=benchmark_return_pct,
        alpha_pct=alpha_pct,
        max_drawdown_pct=max_drawdown_pct,
        warnings=warnings or [],
        sharpe_ratio=sharpe_ratio,
        sortino_ratio=sortino_ratio,
        calmar_ratio=calmar_ratio,
        win_rate_pct=win_rate_pct,
        profit_factor=profit_factor,
        avg_trade_return_pct=avg_trade_return_pct,
    )


def make_backtest_leaderboard_entry(
    account_name: str = "acct1",
    *,
    run_id: int = 1,
    run_name: str | None = None,
    strategy: str = "trend_v1",
    start_date: str = "2026-01-01",
    end_date: str = "2026-03-01",
    created_at: str = "2026-03-17T01:00:00Z",
    trade_count: int = 5,
    ending_equity: float = 10_000.0,
    total_return_pct: float = 0.0,
    max_drawdown_pct: float = -1.0,
    benchmark_return_pct: float | None = None,
    alpha_pct: float | None = None,
) -> BacktestLeaderboardEntry:
    return BacktestLeaderboardEntry(
        run_id=run_id,
        run_name=run_name,
        account_name=account_name,
        strategy=strategy,
        start_date=start_date,
        end_date=end_date,
        created_at=created_at,
        trade_count=trade_count,
        ending_equity=ending_equity,
        total_return_pct=total_return_pct,
        max_drawdown_pct=max_drawdown_pct,
        benchmark_return_pct=benchmark_return_pct,
        alpha_pct=alpha_pct,
    )


__all__ = [
    "create_backtest_account",
    "install_backtest_market_data",
    "make_backtest_config",
    "make_backtest_leaderboard_entry",
    "make_backtest_result",
    "make_fake_close_history",
    "make_walk_forward_config",
]
