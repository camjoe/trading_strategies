from __future__ import annotations

import pandas as pd
import pytest

from trading.services.accounts import create_account
from trading.backtesting.backtest import BacktestConfig, run_backtest
import trading.backtesting.services.report_service as report_service
from trading.backtesting.report_models import BacktestFullReport


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
        tickers_file="trading/config/trade_universe.txt",
        universe_history_dir=None,
        start="2026-01-01",
        end="2026-03-01",
        lookback_months=None,
        slippage_bps=1.0,
        fee_per_trade=0.0,
        run_name="contract",
        allow_approximate_leaps=False,
    )


def test_report_service_contract_builds_typed_model(conn, monkeypatch: pytest.MonkeyPatch) -> None:
    create_account(conn, "acct_report_service", "trend_v1", 10000.0, "SPY")
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

    result = run_backtest(conn, _backtest_config("acct_report_service"))

    monkeypatch.setattr(
        report_service,
        "fetch_benchmark_close",
        lambda _ticker, _start, _end: pd.Series([100.0, 102.0]),
    )

    report = report_service.fetch_backtest_report_data(conn, run_id=result.run_id)

    assert isinstance(report, BacktestFullReport)
    assert report.summary.run_id == result.run_id
    assert report.summary.account_name == "acct_report_service"
    assert report.summary.sharpe_ratio is not None
    assert report.summary.calmar_ratio is not None


def test_report_service_contract_handles_benchmark_fetch_error(conn, monkeypatch: pytest.MonkeyPatch) -> None:
    create_account(conn, "acct_report_error", "trend_v1", 10000.0, "SPY")
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

    result = run_backtest(conn, _backtest_config("acct_report_error"))

    monkeypatch.setattr(
        report_service,
        "fetch_benchmark_close",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("boom")),
    )

    report = report_service.fetch_backtest_report_data(conn, run_id=result.run_id)

    assert report.benchmark_return_pct is None
    assert report.alpha_pct is None
    assert report.summary.sharpe_ratio is not None


def test_fetch_backtest_report_data_raises_for_missing_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(report_service, "fetch_backtest_report_run", lambda *_args, **_kwargs: None)

    with pytest.raises(ValueError, match="not found"):
        report_service.fetch_backtest_report_data(object(), run_id=999)


def test_fetch_backtest_report_data_raises_when_no_snapshots(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        report_service,
        "fetch_backtest_report_run",
        lambda *_args, **_kwargs: {
            "id": 1,
            "run_name": "r1",
            "account_name": "acct",
            "strategy": "trend",
            "start_date": "2026-01-01",
            "end_date": "2026-01-31",
            "created_at": "2026-01-31T00:00:00Z",
            "slippage_bps": 1.0,
            "fee_per_trade": 0.0,
            "tickers_file": "tickers.txt",
            "warnings": None,
            "benchmark_ticker": "SPY",
            "initial_cash": 10000.0,
            "notes": None,
        },
    )
    monkeypatch.setattr(report_service, "fetch_backtest_report_snapshots", lambda *_a, **_k: [])
    monkeypatch.setattr(report_service, "fetch_backtest_report_trades", lambda *_a, **_k: [])

    with pytest.raises(ValueError, match="No snapshots"):
        report_service.fetch_backtest_report_data(object(), run_id=1)


def test_fetch_latest_backtest_run_for_account_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(report_service, "_repo_fetch_latest_backtest_run_for_account", lambda *_a, **_k: None)
    assert report_service.fetch_latest_backtest_run_for_account(object(), account_name="acct") is None


def test_latest_and_recent_backtest_run_wrappers_map_repository_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    row = {
        "id": 12,
        "run_name": "weekly-run",
        "account_name": "acct",
        "strategy": "trend",
        "start_date": "2026-01-01",
        "end_date": "2026-01-31",
        "created_at": "2026-01-31T00:00:00Z",
        "slippage_bps": "1.25",
        "fee_per_trade": "0.5",
        "tickers_file": "trade_universe.txt",
    }
    monkeypatch.setattr(report_service, "_repo_fetch_latest_backtest_run_for_account", lambda *_a, **_k: row)
    monkeypatch.setattr(report_service, "_repo_fetch_recent_backtest_runs", lambda *_a, **_k: [row, row])

    latest = report_service.fetch_latest_backtest_run_for_account(object(), account_name="acct")
    recent = report_service.fetch_recent_backtest_runs(object(), limit=2)

    assert latest == {
        "runId": 12,
        "runName": "weekly-run",
        "accountName": "acct",
        "strategy": "trend",
        "startDate": "2026-01-01",
        "endDate": "2026-01-31",
        "createdAt": "2026-01-31T00:00:00Z",
        "slippageBps": 1.25,
        "feePerTrade": 0.5,
        "tickersFile": "trade_universe.txt",
    }
    assert recent == [latest, latest]
