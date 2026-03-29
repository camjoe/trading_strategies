from __future__ import annotations

import pandas as pd
import pytest

from trading.accounts import create_account
from trading.backtesting.backtest import BacktestConfig, run_backtest
from trading.backtesting.repositories.report_repository import (
    fetch_backtest_report_run,
    fetch_backtest_report_snapshots,
    fetch_backtest_report_trades,
)


def _fake_close_history(tickers: list[str]) -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=40, freq="B")
    data: dict[str, list[float]] = {}
    for i, ticker in enumerate(tickers):
        base = 100.0 + (i * 5.0)
        values = [base + (j * 0.8) for j in range(30)] + [base + 24.0 - ((j - 30) * 0.9) for j in range(30, 40)]
        data[ticker] = values
    return pd.DataFrame(data, index=idx)


def _backtest_config(account_name: str) -> BacktestConfig:
    return BacktestConfig(
        account_name=account_name,
        tickers_file="trading/trade_universe.txt",
        universe_history_dir=None,
        start="2026-01-01",
        end="2026-03-01",
        lookback_months=None,
        slippage_bps=1.0,
        fee_per_trade=0.0,
        run_name="contract",
        allow_approximate_leaps=False,
    )


def test_report_repository_contract_returns_rows(conn, monkeypatch: pytest.MonkeyPatch) -> None:
    create_account(conn, "acct_report_repo", "trend_v1", 10000.0, "SPY")
    monkeypatch.setattr("trading.backtesting.backtest.load_tickers_from_file", lambda _path: ["AAPL"])
    monkeypatch.setattr(
        "trading.backtesting.backtest.fetch_close_history",
        lambda _tickers, _start, _end: _fake_close_history(_tickers),
    )
    monkeypatch.setattr(
        "trading.backtesting.backtest.fetch_benchmark_close",
        lambda _ticker, _start, _end: pd.Series(
            [100.0, 102.0],
            index=pd.date_range("2026-01-01", periods=2, freq="B"),
        ),
    )

    result = run_backtest(conn, _backtest_config("acct_report_repo"))

    run_row = fetch_backtest_report_run(conn, result.run_id)
    snapshot_rows = fetch_backtest_report_snapshots(conn, result.run_id)
    trade_rows = fetch_backtest_report_trades(conn, result.run_id)

    assert run_row is not None
    assert len(snapshot_rows) >= 2
    assert isinstance(trade_rows, list)