import pytest

from trading.models import AccountConfig
from trading.repositories.snapshots import EquitySnapshotRepository
from trading.services.accounts import create_account, get_account
from trading.services.reporting import account_report, compare_strategies, show_snapshots, snapshot_account
from trading.services.reporting.presentation import positions_summary_text
from tests.support.reporting import insert_trade, make_evaluation_artifact


def test_positions_summary_text_sorts_and_truncates() -> None:
    count, text = positions_summary_text({"MSFT": 2.0, "AAPL": 5.0})
    assert count == 2
    assert text.startswith("AAPL")

    truncated_count, truncated_text = positions_summary_text({f"T{i}": float(i) for i in range(7)})
    assert truncated_count == 7
    assert truncated_text.endswith(", ...")


def test_account_report_prints_benchmark_and_evaluation(conn, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    create_account(conn, "acct_report_out", "Trend", 1000.0, "SPY")
    account = get_account(conn, "acct_report_out")
    insert_trade(conn, account["id"], "AAPL", 2.0, 100.0)
    conn.commit()

    monkeypatch.setattr(
        "trading.services.analysis.portfolio.fetch_latest_prices",
        lambda _tickers, **_kwargs: {"AAPL": 120.0},
    )
    monkeypatch.setattr(
        "trading.services.analysis.portfolio.benchmark_stats",
        lambda *_args, **_kwargs: (1050.0, 5.0),
    )
    monkeypatch.setattr(
        "trading.services.reporting.presentation.fetch_strategy_evaluation_for_account_row",
        lambda *_args, **_kwargs: make_evaluation_artifact(
            account_id=account["id"],
            account_name="acct_report_out",
            backtest_return_pct=12.5,
            backtest_trade_count=18,
            paper_live_mode="paper",
            paper_live_return_pct=4.0,
            paper_live_snapshot_count=6,
            blended_score=9.25,
            overall_confidence=0.62,
        ),
    )

    stats, positions = account_report(conn, "acct_report_out")
    out = capsys.readouterr().out

    assert stats["equity"] == pytest.approx(1040.0)
    assert positions == {"AAPL": 2.0}
    assert "Display Name: acct_report_out" in out
    assert "Benchmark Equity: 1050.00" in out
    assert "Account Alpha vs Benchmark %: -1.00" in out
    assert "Evaluation Summary: backtest=12.50% (18 trades) | paper=4.00% (6 snapshots)" in out
    # No freshness on this artifact → advisory shows N/A.
    assert "backtest_age=N/A" in out


def test_account_report_prints_unavailable_benchmark_and_leaps_fields(
    conn, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    create_account(
        conn,
        "acct_leaps",
        "Trend",
        5000.0,
        "SPY",
        config=AccountConfig(
            instrument_mode="leaps",
            option_strike_offset_pct=5.0,
            option_min_dte=120,
            option_max_dte=365,
            option_type="call",
            target_delta_min=0.2,
            target_delta_max=0.4,
            iv_rank_min=20.0,
            iv_rank_max=70.0,
            max_premium_per_trade=500.0,
            max_contracts_per_trade=2,
            roll_dte_threshold=45,
            option_profit_take_pct=30.0,
            option_max_loss_pct=20.0,
        ),
    )
    monkeypatch.setattr("trading.services.analysis.portfolio.fetch_latest_prices", lambda _tickers, **_kwargs: {})
    monkeypatch.setattr(
        "trading.services.analysis.portfolio.benchmark_stats", lambda *_args, **_kwargs: (None, None)
    )

    account_report(conn, "acct_leaps")
    out = capsys.readouterr().out

    assert "Benchmark comparison: unavailable (price history not found)" in out
    assert "LEAPs Parameters:" in out
    assert "LEAPs Options Filters:" in out
    assert "LEAPs/Options Risk Limits:" in out


def test_account_report_shows_rotation_active_strategy(conn, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    # The active strategy is the default book's open assignment (ADR 014).
    from trading.services.books.book_assignments import sync_default_book_assignment

    create_account(conn, "acct_rot", "Trend", 1000.0, "SPY")
    account = get_account(conn, "acct_rot")
    sync_default_book_assignment(
        conn,
        account_id=account["id"],
        strategy_name="mean_reversion",
        now_iso="2026-01-01T00:00:00Z",
    )

    monkeypatch.setattr("trading.services.analysis.portfolio.fetch_latest_prices", lambda _tickers, **_kwargs: {})
    monkeypatch.setattr(
        "trading.services.analysis.portfolio.benchmark_stats", lambda *_args, **_kwargs: (None, None)
    )

    account_report(conn, "acct_rot")
    out = capsys.readouterr().out
    assert "active_strategy=mean_reversion" in out


def test_compare_strategies_outputs_summary_and_truncates_positions(
    conn, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    create_account(conn, "acct_many", "Trend", 10000.0, "SPY", config=AccountConfig(descriptive_name="Many"))
    account = get_account(conn, "acct_many")

    tickers = ["AAPL", "AMZN", "GOOG", "META", "MSFT", "NVDA"]
    for index, ticker in enumerate(tickers):
        insert_trade(conn, account["id"], ticker, 1.0, 100.0 + index, trade_time=f"2026-01-01T00:00:0{index}Z")
    conn.commit()

    monkeypatch.setattr(
        "trading.services.analysis.portfolio.fetch_latest_prices",
        lambda symbols, **_kwargs: {symbol: 110.0 for symbol in symbols},
    )
    monkeypatch.setattr(
        "trading.services.reporting.presentation.benchmark_stats", lambda *_args, **_kwargs: (10100.0, 1.0)
    )
    monkeypatch.setattr(
        "trading.services.reporting.presentation.fetch_strategy_evaluation_for_account_row",
        lambda *_args, **_kwargs: make_evaluation_artifact(
            account_id=account["id"],
            account_name="acct_many",
        ),
    )
    monkeypatch.setattr("trading.services.reporting.presentation.infer_overall_trend", lambda *_args, **_kwargs: "up")

    compare_strategies(conn, lookback=5)
    out = capsys.readouterr().out
    assert "Account policy comparison (current paper account state):" in out
    assert "display_name=Many" in out
    assert "positions: AAPL:1.00, AMZN:1.00, GOOG:1.00, META:1.00, MSFT:1.00, ..." in out


def test_compare_strategies_handles_empty_accounts_and_no_positions(
    conn, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    compare_strategies(conn, lookback=5)
    assert "No paper accounts found." in capsys.readouterr().out

    create_account(conn, "acct_none", "Trend", 1000.0, "SPY", config=AccountConfig(descriptive_name="No Trades"))
    monkeypatch.setattr(
        "trading.services.reporting.presentation.benchmark_stats", lambda *_args, **_kwargs: (None, None)
    )

    compare_strategies(conn, lookback=5)
    out = capsys.readouterr().out
    assert "positions: none" in out


def test_snapshot_account_inserts_and_defaults_time(conn, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    create_account(conn, "acct_snap", "Trend", 1000.0, "SPY")
    monkeypatch.setattr(
        "trading.services.reporting.presentation.account_report",
        lambda _conn, _name, **_kwargs: (
            {
                "cash": 900.0,
                "market_value": 150.0,
                "equity": 1050.0,
                "realized_pnl": 20.0,
                "unrealized_pnl": 30.0,
            },
            {"AAPL": 1.0},
        ),
    )
    monkeypatch.setattr("trading.services.reporting.presentation.utc_now_iso", lambda: "2099-01-01T00:00:00Z")

    snapshot_account(conn, "acct_snap", snapshot_time=None)
    assert "Snapshot saved." in capsys.readouterr().out

    account = get_account(conn, "acct_snap")
    row = conn.execute(
        """
        SELECT s.snapshot_time, s.equity
        FROM equity_snapshots s
        JOIN books b ON b.id = s.book_id
        WHERE b.account_id = ?
        """,
        (account["id"],),
    ).fetchone()
    assert row["snapshot_time"] == "2099-01-01T00:00:00Z"
    assert float(row["equity"]) == pytest.approx(1050.0)


def test_show_snapshots_handles_empty_and_rows(conn, capsys) -> None:
    create_account(conn, "acct_show", "Trend", 1000.0, "SPY")

    show_snapshots(conn, "acct_show", limit=5)
    assert "No snapshots found." in capsys.readouterr().out

    account = get_account(conn, "acct_show")
    EquitySnapshotRepository(conn).insert(
        account_id=int(account["id"]),
        snapshot_time="2026-03-01T00:00:00Z",
        cash=900.0,
        market_value=100.0,
        equity=1000.0,
        realized_pnl=10.0,
        unrealized_pnl=15.0,
    )

    show_snapshots(conn, "acct_show", limit=5)
    out = capsys.readouterr().out
    assert "Snapshot history (latest 5) for acct_show:" in out
    assert "equity=1000.00" in out


def test_account_report_shows_stale_backtest_freshness(conn, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    from trading.models.evaluation import BacktestFreshness

    create_account(conn, "acct_fresh", "Trend", 1000.0, "SPY")
    monkeypatch.setattr("trading.services.analysis.portfolio.fetch_latest_prices", lambda _t, **_k: {})
    monkeypatch.setattr("trading.services.reporting.presentation.benchmark_stats", lambda *_a, **_k: (None, None))
    account = get_account(conn, "acct_fresh")
    monkeypatch.setattr(
        "trading.services.reporting.presentation.fetch_strategy_evaluation_for_account_row",
        lambda *_a, **_k: make_evaluation_artifact(
            account_id=account["id"],
            account_name="acct_fresh",
            backtest_return_pct=8.0,
            backtest_trade_count=10,
            blended_score=5.0,
            overall_confidence=0.5,
            backtest_freshness=BacktestFreshness(available=True, age_days=6.0, stale_threshold_days=3, is_stale=True),
        ),
    )

    account_report(conn, "acct_fresh")
    out = capsys.readouterr().out

    assert "backtest_age=6.0d (stale)" in out
