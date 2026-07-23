from __future__ import annotations

import pandas as pd
import pytest

import trading.backtesting.services.report_service as report_service
from tests.support.backtesting import create_backtest_account, make_backtest_config
from trading.backtesting.backtest import run_backtest
from trading.backtesting.report_models import BacktestFullReport


def test_report_service_contract_builds_typed_model(
    conn,
    bt_market_data,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_backtest_account(conn, "acct_report_service")
    bt_market_data(["AAPL"], [100.0, 102.0])

    result = run_backtest(conn, make_backtest_config("acct_report_service", slippage_bps=1.0, run_name="contract"))

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


def test_report_service_contract_handles_benchmark_fetch_error(
    conn,
    bt_market_data,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_backtest_account(conn, "acct_report_error")
    bt_market_data(["AAPL"], [100.0, 102.0])

    result = run_backtest(conn, make_backtest_config("acct_report_error", slippage_bps=1.0, run_name="contract"))

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
