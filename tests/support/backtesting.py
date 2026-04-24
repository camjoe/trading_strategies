from __future__ import annotations

import pandas as pd

from trading.models import AccountConfig
from trading.services.accounts import create_account
from trading.backtesting.backtest import BacktestConfig, WalkForwardConfig


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


__all__ = [
    "create_backtest_account",
    "install_backtest_market_data",
    "make_backtest_config",
    "make_fake_close_history",
    "make_walk_forward_config",
]
