from __future__ import annotations

import pytest

import backtesting.services.report_service as report_service
from backtesting.composition import run_backtest
from backtesting.models.report import BacktestFullReport
from tests.support.backtesting import (
    create_backtest_account,
    make_backtest_config,
    seed_backtest_run,
    stub_market_data_provider,
)


def test_report_summary_does_not_build_the_per_row_models(conn, monkeypatch, bt_market_data) -> None:
    """A summary caller must not pay for the snapshot and trade lists it discards.

    It used to build the whole ``BacktestFullReport`` and return ``.summary``, so
    the account-comparison page constructed a model per snapshot and per trade,
    per account, and threw all of them away.
    """
    create_backtest_account(conn, "acct_summary_only")
    bt_market_data(["AAPL"], [100.0, 102.0])
    result = run_backtest(
        conn, make_backtest_config("acct_summary_only", run_name="summary-only"), provider=stub_market_data_provider()
    )

    def _must_not_build(*_args, **_kwargs):
        raise AssertionError("the summary path must not construct per-row report models")

    monkeypatch.setattr(report_service, "BacktestReportSnapshot", _must_not_build)
    monkeypatch.setattr(report_service, "BacktestReportTrade", _must_not_build)

    summary = report_service.fetch_backtest_report_summary(conn, result.run_id)

    assert summary.run_id == result.run_id
    # The metrics still come off the full curve and trade list.
    assert summary.trade_count > 0
    assert summary.max_drawdown_pct <= 0.0


def test_report_service_contract_builds_typed_model(conn, bt_market_data) -> None:
    create_backtest_account(conn, "acct_report_service")
    bt_market_data(["AAPL"], [100.0, 102.0])

    result = run_backtest(
        conn,
        make_backtest_config("acct_report_service", slippage_bps=1.0, run_name="contract"),
        provider=stub_market_data_provider(),
    )

    report = report_service.fetch_backtest_report_data(conn, run_id=result.run_id)

    assert isinstance(report, BacktestFullReport)
    assert report.summary.run_id == result.run_id
    assert report.summary.account_name == "acct_report_service"
    assert report.summary.sharpe_ratio is not None
    assert report.summary.calmar_ratio is not None


def test_report_reads_the_benchmark_frozen_on_the_run(conn, bt_market_data) -> None:
    """The read touches no market data — the run stored its own benchmark return.

    The report path used to recompute this, resolving the ticker through
    ``accounts.benchmark_ticker`` (the account's *current* value) and needing a
    provider injected at read time. Both were wrong: changing an account's
    benchmark retroactively re-benchmarked its past runs, and the leaderboard
    path, which injected no provider, silently produced no benchmark at all.
    """
    create_backtest_account(conn, "acct_report_frozen")
    bt_market_data(["AAPL"], [100.0, 102.0])

    result = run_backtest(
        conn,
        make_backtest_config("acct_report_frozen", slippage_bps=1.0, run_name="frozen"),
        provider=stub_market_data_provider(),
    )

    report = report_service.fetch_backtest_report_data(conn, run_id=result.run_id)

    assert report.benchmark_return_pct == pytest.approx(result.benchmark_return_pct)
    assert report.alpha_pct == pytest.approx(report.summary.total_return_pct - report.benchmark_return_pct)


def test_report_reports_no_alpha_when_the_benchmark_window_was_too_short(conn, bt_market_data) -> None:
    """``benchmark_return_pct`` yields None on a window with fewer than two usable closes."""
    create_backtest_account(conn, "acct_report_null_bench")
    bt_market_data(["AAPL"], [100.0, 102.0])

    result = run_backtest(
        conn,
        make_backtest_config("acct_report_null_bench", slippage_bps=1.0, run_name="nullbench"),
        provider=stub_market_data_provider(),
    )
    conn.execute("UPDATE backtest_runs SET benchmark_return_pct = NULL WHERE id = ?", (result.run_id,))
    conn.commit()

    report = report_service.fetch_backtest_report_data(conn, run_id=result.run_id)

    assert report.benchmark_return_pct is None
    assert report.alpha_pct is None
    assert report.summary.sharpe_ratio is not None


def test_fetch_backtest_report_data_raises_for_missing_run(conn) -> None:
    with pytest.raises(ValueError, match="not found"):
        report_service.fetch_backtest_report_data(conn, run_id=999)


def test_fetch_backtest_report_data_raises_when_no_snapshots(conn) -> None:
    """A run header with no equity rows has no curve to report on."""
    run_id = seed_backtest_run(conn, account_name="acct_no_snaps")
    conn.execute("DELETE FROM backtest_equity_snapshots WHERE run_id = ?", (run_id,))
    conn.commit()

    with pytest.raises(ValueError, match="No snapshots"):
        report_service.fetch_backtest_report_data(conn, run_id=run_id)


def test_latest_run_reads_return_none_for_an_account_with_no_runs(conn) -> None:
    create_backtest_account(conn, "acct_no_runs")

    assert report_service.fetch_latest_backtest_run_for_account(conn, account_name="acct_no_runs") is None
    assert report_service.fetch_latest_backtest_run_id_for_account(conn, account_name="acct_no_runs") is None


def test_latest_and_recent_backtest_run_wrappers_map_repository_rows(conn) -> None:
    seed_backtest_run(conn, account_name="acct_wrappers", run_name="older")
    newest = seed_backtest_run(conn, account_name="acct_wrappers", run_name="weekly-run", create_account_first=False)

    latest = report_service.fetch_latest_backtest_run_for_account(conn, account_name="acct_wrappers")
    recent = report_service.fetch_recent_backtest_runs(conn, limit=2)
    latest_id = report_service.fetch_latest_backtest_run_id_for_account(conn, account_name="acct_wrappers")

    assert latest is not None
    # Typed records, not transport dicts: camelCase is the web app's business.
    assert latest.run_id == newest
    assert latest.run_name == "weekly-run"
    assert latest.account_name == "acct_wrappers"
    assert latest.strategy == "trend_v1"
    assert isinstance(latest.slippage_bps, float)
    assert [row.run_name for row in recent] == ["weekly-run", "older"]
    # The id read is the same row projected differently, not a second query.
    assert latest_id == newest


def test_report_summary_splits_the_stored_warnings_column(conn) -> None:
    """``backtest_runs.warnings`` is a ``" | "``-joined TEXT column, not a list.

    Assigning it straight to the ``list[str]`` field left a ``str`` there, so a
    caller iterating ``summary.warnings`` walked characters instead of entries.
    """
    run_id = seed_backtest_run(
        conn,
        account_name="acct_warnings",
        warnings=["short history", "approximate leaps"],
    )

    report = report_service.fetch_backtest_report_data(conn, run_id=run_id)

    assert report.summary.warnings == ["short history", "approximate leaps"]
