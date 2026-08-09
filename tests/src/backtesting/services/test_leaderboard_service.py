from __future__ import annotations

import pytest

import backtesting.services.leaderboard_service as leaderboard_service
from tests.support.backtesting import seed_backtest_run


def _entries(conn, **kwargs):
    return leaderboard_service.fetch_backtest_leaderboard_entries(
        conn,
        limit=kwargs.pop("limit", 10),
        account_name=kwargs.pop("account_name", None),
        strategy=kwargs.pop("strategy", None),
    )


def test_leaderboard_service_rejects_non_positive_limit(conn) -> None:
    with pytest.raises(ValueError, match="limit must be > 0"):
        _entries(conn, limit=0)


def test_leaderboard_service_ranks_by_total_return(conn) -> None:
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
