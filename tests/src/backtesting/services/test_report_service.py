from __future__ import annotations

import pandas as pd
import pytest

import backtesting.services.report_service as report_service
from backtesting.backtest import run_backtest
from backtesting.report_models import BacktestFullReport
from tests.support.backtesting import create_backtest_account, make_backtest_config


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
        lambda _ticker, _start, _end, **_kwargs: pd.Series([100.0, 102.0]),
    )

    report = report_service.fetch_backtest_report_data(conn, run_id=result.run_id, provider=object())

    assert isinstance(report, BacktestFullReport)
    assert report.summary.run_id == result.run_id
    assert report.summary.account_name == "acct_report_service"
    assert report.summary.sharpe_ratio is not None
    assert report.summary.calmar_ratio is not None
    # An injected provider means the benchmark leg actually ran.
    assert report.benchmark_return_pct is not None
    assert report.alpha_pct is not None


def test_report_data_forwards_the_injected_provider_to_the_benchmark_fetch(
    conn,
    bt_market_data,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The provider must reach ``fetch_benchmark_close``.

    It previously did not: the report read called the fetch with no provider at
    all, so ``require_provider`` raised and the swallowing ``except`` turned
    every report into a benchmark-less one plus a logged traceback.
    """
    create_backtest_account(conn, "acct_report_provider")
    bt_market_data(["AAPL"], [100.0, 102.0])

    result = run_backtest(conn, make_backtest_config("acct_report_provider", slippage_bps=1.0, run_name="contract"))

    injected = object()
    seen: list[object] = []

    def _capture(_ticker, _start, _end, *, provider=None):
        seen.append(provider)
        return pd.Series([100.0, 102.0])

    monkeypatch.setattr(report_service, "fetch_benchmark_close", _capture)

    report_service.fetch_backtest_report_data(conn, run_id=result.run_id, provider=injected)

    assert seen == [injected]


def test_report_data_without_a_provider_skips_the_benchmark(
    conn,
    bt_market_data,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No provider means no benchmark — not an attempt that raises and is swallowed."""
    create_backtest_account(conn, "acct_report_no_provider")
    bt_market_data(["AAPL"], [100.0, 102.0])

    result = run_backtest(conn, make_backtest_config("acct_report_no_provider", slippage_bps=1.0, run_name="contract"))

    calls: list[object] = []

    def _record(*args, **kwargs):
        calls.append((args, kwargs))
        return pd.Series([100.0, 102.0])

    monkeypatch.setattr(report_service, "fetch_benchmark_close", _record)

    report = report_service.fetch_backtest_report_data(conn, run_id=result.run_id)

    assert calls == []
    assert report.benchmark_return_pct is None
    assert report.alpha_pct is None
    assert report.summary.sharpe_ratio is not None


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

    report = report_service.fetch_backtest_report_data(conn, run_id=result.run_id, provider=object())

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
        "tickers_file": "default.txt",
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
        "tickersFile": "default.txt",
    }
    assert recent == [latest, latest]


def test_report_summary_splits_the_stored_warnings_column(monkeypatch: pytest.MonkeyPatch) -> None:
    """``backtest_runs.warnings`` is a ``" | "``-joined TEXT column, not a list.

    Assigning it straight to the ``list[str]`` field left a ``str`` there, so a
    caller iterating ``summary.warnings`` walked characters instead of entries.
    """
    monkeypatch.setattr(
        report_service,
        "fetch_backtest_report_run",
        lambda *_a, **_k: {
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
            "warnings": "short history | approximate leaps",
            "benchmark_ticker": "SPY",
            "initial_cash": 10000.0,
            "notes": None,
        },
    )
    snapshot = {
        "snapshot_time": "2026-01-01",
        "cash": 0.0,
        "market_value": 0.0,
        "equity": 10000.0,
        "realized_pnl": 0.0,
        "unrealized_pnl": 0.0,
    }
    monkeypatch.setattr(report_service, "fetch_backtest_report_snapshots", lambda *_a, **_k: [snapshot, snapshot])
    monkeypatch.setattr(report_service, "fetch_backtest_report_trades", lambda *_a, **_k: [])

    report = report_service.fetch_backtest_report_data(object(), run_id=1)

    assert report.summary.warnings == ["short history", "approximate leaps"]
