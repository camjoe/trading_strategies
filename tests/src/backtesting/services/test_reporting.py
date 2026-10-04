from __future__ import annotations

import pytest

import backtesting.services.reporting as reporting
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

    monkeypatch.setattr(reporting, "BacktestReportSnapshot", _must_not_build)
    monkeypatch.setattr(reporting, "BacktestReportTrade", _must_not_build)

    summary = reporting.fetch_report_summary(conn, result.run_id)

    assert summary.run_id == result.run_id
    # The metrics still come off the full curve and trade list.
    assert summary.trade_count > 0
    assert summary.max_drawdown_pct <= 0.0


def test_reporting_contract_builds_typed_model(conn, bt_market_data) -> None:
    create_backtest_account(conn, "acct_report_service")
    bt_market_data(["AAPL"], [100.0, 102.0])

    result = run_backtest(
        conn,
        make_backtest_config("acct_report_service", slippage_bps=1.0, run_name="contract"),
        provider=stub_market_data_provider(),
    )

    report = reporting.fetch_report(conn, run_id=result.run_id)

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

    report = reporting.fetch_report(conn, run_id=result.run_id)

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

    report = reporting.fetch_report(conn, run_id=result.run_id)

    assert report.benchmark_return_pct is None
    assert report.alpha_pct is None
    assert report.summary.sharpe_ratio is not None


def test_fetch_report_raises_for_missing_run(conn) -> None:
    with pytest.raises(ValueError, match="not found"):
        reporting.fetch_report(conn, run_id=999)


def test_fetch_report_raises_when_no_snapshots(conn) -> None:
    """A run header with no equity rows has no curve to report on."""
    run_id = seed_backtest_run(conn, account_name="acct_no_snaps")
    conn.execute("DELETE FROM backtest_equity_snapshots WHERE run_id = ?", (run_id,))
    conn.commit()

    with pytest.raises(ValueError, match="No snapshots"):
        reporting.fetch_report(conn, run_id=run_id)


def test_latest_run_reads_return_none_for_an_account_with_no_runs(conn) -> None:
    create_backtest_account(conn, "acct_no_runs")

    assert reporting.fetch_latest_run_for_account(conn, account_name="acct_no_runs") is None
    assert reporting.fetch_latest_run_id_for_account(conn, account_name="acct_no_runs") is None


def test_latest_and_recent_backtest_run_wrappers_map_repository_rows(conn) -> None:
    seed_backtest_run(conn, account_name="acct_wrappers", run_name="older")
    newest = seed_backtest_run(conn, account_name="acct_wrappers", run_name="weekly-run", create_account_first=False)

    latest = reporting.fetch_latest_run_for_account(conn, account_name="acct_wrappers")
    recent = reporting.fetch_recent_runs(conn, limit=2)
    latest_id = reporting.fetch_latest_run_id_for_account(conn, account_name="acct_wrappers")

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

    report = reporting.fetch_report(conn, run_id=run_id)

    assert report.summary.warnings == ["short history", "approximate leaps"]


# ---------------------------------------------------------------------------
# Leaderboard: the same tables and performance math, ranked across runs
# ---------------------------------------------------------------------------


def _entries(conn, **kwargs):
    return reporting.fetch_leaderboard(
        conn,
        limit=kwargs.pop("limit", 10),
        account_name=kwargs.pop("account_name", None),
        strategy=kwargs.pop("strategy", None),
    )


def test_leaderboard_rejects_non_positive_limit(conn) -> None:
    with pytest.raises(ValueError, match="limit must be > 0"):
        _entries(conn, limit=0)


def test_leaderboard_ranks_by_total_return(conn) -> None:
    seed_backtest_run(conn, account_name="acct_rank", run_name="weaker", start_equity=1_000.0, end_equity=1_050.0)
    seed_backtest_run(
        conn,
        account_name="acct_rank",
        run_name="stronger",
        start_equity=1_000.0,
        end_equity=1_100.0,
        create_account_first=False,
    )

    entries = _entries(conn, account_name="acct_rank")

    assert [entry.run_name for entry in entries] == ["stronger", "weaker"]


def test_leaderboard_ranks_across_all_runs_not_just_the_newest(conn) -> None:
    """The limit selects the best runs, not the newest ones.

    Ranking used to happen in Python over whatever the SQL's ``created_at DESC``
    ordering had already truncated to, so the best run fell off the board as soon
    as ``limit`` newer runs existed — the opposite of what a leaderboard is for.
    """
    best = seed_backtest_run(conn, account_name="acct_deep", run_name="old-best", end_equity=9_000.0)
    for index in range(5):
        seed_backtest_run(
            conn,
            account_name="acct_deep",
            run_name=f"newer-{index}",
            end_equity=1_010.0,
            create_account_first=False,
        )

    entries = _entries(conn, account_name="acct_deep", limit=3)

    assert [entry.run_id for entry in entries][0] == best
    assert len(entries) == 3


def test_leaderboard_fills_the_limit_past_unrankable_runs(conn) -> None:
    """A run with no equity marks is dropped before the limit, not after it."""
    seed_backtest_run(conn, account_name="acct_fill", run_name="keep-1", end_equity=1_100.0)
    orphan = seed_backtest_run(conn, account_name="acct_fill", run_name="orphan", create_account_first=False)
    seed_backtest_run(
        conn, account_name="acct_fill", run_name="keep-2", end_equity=1_050.0, create_account_first=False
    )
    conn.execute("DELETE FROM backtest_equity_snapshots WHERE run_id = ?", (orphan,))
    conn.commit()

    entries = _entries(conn, account_name="acct_fill", limit=2)

    assert [entry.run_name for entry in entries] == ["keep-1", "keep-2"]


def test_leaderboard_carries_the_stored_benchmark_and_derives_alpha(conn) -> None:
    # 1000 -> 1050 is +5%; the run's frozen benchmark is +1%, so alpha is +4%.
    seed_backtest_run(
        conn,
        account_name="acct_alpha",
        start_equity=1_000.0,
        end_equity=1_050.0,
        benchmark_return_pct=1.0,
    )

    (entry,) = _entries(conn, account_name="acct_alpha")

    assert entry.total_return_pct == pytest.approx(5.0)
    assert entry.benchmark_return_pct == pytest.approx(1.0)
    assert entry.alpha_pct == pytest.approx(4.0)


def test_leaderboard_reports_no_alpha_when_the_benchmark_window_was_too_short(conn) -> None:
    # benchmark_return_pct() yields None on a window with fewer than two usable closes.
    seed_backtest_run(conn, account_name="acct_no_bench", benchmark_return_pct=None)

    (entry,) = _entries(conn, account_name="acct_no_bench")

    assert entry.benchmark_return_pct is None
    assert entry.alpha_pct is None


def test_leaderboard_computes_trade_metrics_from_the_run_executions(conn) -> None:
    seed_backtest_run(
        conn,
        account_name="acct_trades",
        trades=[("AAPL", "buy", 1.0, 100.0), ("AAPL", "sell", 1.0, 110.0)],
    )

    (entry,) = _entries(conn, account_name="acct_trades")

    assert entry.trade_count == 2
    assert entry.win_rate_pct == pytest.approx(100.0)


def test_leaderboard_filters_by_account_and_strategy(conn) -> None:
    seed_backtest_run(conn, account_name="acct_one", strategy_name="trend_v1")
    seed_backtest_run(conn, account_name="acct_two", strategy_name="mean_reversion_v1")

    assert [e.account_name for e in _entries(conn, account_name="acct_one")] == ["acct_one"]
    assert [e.strategy for e in _entries(conn, strategy="mean_reversion")] == ["mean_reversion_v1"]


def test_leaderboard_filter_resolves_an_alias_to_the_canonical_key(conn) -> None:
    """An alias has to reach the runs it names.

    Runs store the canonical strategy key, so a filter passed straight through
    matches nothing and returns an empty board — which reads identically to "this
    strategy has no runs" rather than "you used an alias".
    """
    seed_backtest_run(conn, account_name="acct_alias", strategy_name="trend")

    assert [e.strategy for e in _entries(conn, strategy="momentum")] == ["trend"]
    assert [e.strategy for e in _entries(conn, strategy="trend_v1")] == ["trend"]


def test_leaderboard_skips_a_run_with_no_equity_snapshots(conn) -> None:
    """Starting equity comes from a subquery over the run's snapshots — no rows, no ranking.

    A run cannot rank on a return it has no marks to compute, so it drops out
    rather than entering the board with a zero or null figure.
    """
    kept = seed_backtest_run(conn, account_name="acct_partial", run_name="complete")
    orphan = seed_backtest_run(conn, account_name="acct_partial", run_name="no-snapshots", create_account_first=False)
    conn.execute("DELETE FROM backtest_equity_snapshots WHERE run_id = ?", (orphan,))
    conn.commit()

    entries = _entries(conn, account_name="acct_partial")

    assert [entry.run_id for entry in entries] == [kept]
