import pytest

from trading.accounts import create_account, get_account
from trading import reporting
from trading.reporting import (
    account_report,
    build_account_stats,
    compare_strategies,
    format_goal_text,
    infer_overall_trend,
    show_snapshots,
    snapshot_account,
)


def test_build_account_stats_uses_price_map(conn, monkeypatch: pytest.MonkeyPatch) -> None:
    create_account(conn, "acct_report", "Trend", 1000.0, "SPY")
    account = get_account(conn, "acct_report")

    conn.execute(
        """
        INSERT INTO trades (account_id, ticker, side, qty, price, fee, trade_time, note)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (account["id"], "AAPL", "buy", 2, 100, 0, "2026-01-01T00:00:00Z", "entry"),
    )
    conn.commit()

    monkeypatch.setattr("trading.reporting.fetch_latest_prices", lambda _tickers: {"AAPL": 120.0})

    state, prices, market_value, unrealized, equity = build_account_stats(conn, account)

    assert state.cash == pytest.approx(800.0)
    assert prices == {"AAPL": 120.0}
    assert market_value == pytest.approx(240.0)
    assert unrealized == pytest.approx(40.0)
    assert equity == pytest.approx(1040.0)


def test_infer_overall_trend_up(conn) -> None:
    create_account(conn, "acct_trend", "Trend", 1000.0, "SPY")
    account = get_account(conn, "acct_trend")

    snapshots = [980.0, 1000.0, 1015.0]
    for i, equity in enumerate(snapshots, start=1):
        ts = f"2026-01-0{i}T00:00:00Z"
        conn.execute(
            """
            INSERT INTO equity_snapshots (account_id, snapshot_time, cash, market_value, equity, realized_pnl, unrealized_pnl)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (account["id"], ts, equity, 0.0, equity, 0.0, 0.0),
        )
    conn.commit()

    trend = infer_overall_trend(conn, account["id"], current_equity=1030.0, lookback=10)
    assert trend == "up"


def test_infer_overall_trend_insufficient_data(conn) -> None:
    create_account(conn, "acct_short", "Trend", 1000.0, "SPY")
    account = get_account(conn, "acct_short")

    trend = infer_overall_trend(conn, account["id"], current_equity=1000.0, lookback=10)
    assert trend == "insufficient-data"


@pytest.mark.parametrize(
    ("goal_min", "goal_max", "goal_period", "expected"),
    [
        (None, None, "monthly", "not-set"),
        (1.5, 3.5, "weekly", "1.50% to 3.50% per weekly"),
        (2.0, None, "monthly", ">= 2.00% per monthly"),
        (None, 4.0, "quarterly", "<= 4.00% per quarterly"),
    ],
)
def test_format_goal_text_variants(conn, goal_min, goal_max, goal_period, expected: str) -> None:
    create_account(
        conn,
        "acct_goal",
        "Trend",
        1000.0,
        "SPY",
        goal_min_return_pct=goal_min,
        goal_max_return_pct=goal_max,
        goal_period=goal_period,
    )
    account = get_account(conn, "acct_goal")
    assert format_goal_text(account) == expected


def test_infer_overall_trend_down_and_flat(conn) -> None:
    create_account(conn, "acct_trend_df", "Trend", 1000.0, "SPY")
    account = get_account(conn, "acct_trend_df")

    for i, equity in enumerate([1000.0, 995.0, 990.0], start=1):
        ts = f"2026-02-0{i}T00:00:00Z"
        conn.execute(
            """
            INSERT INTO equity_snapshots (account_id, snapshot_time, cash, market_value, equity, realized_pnl, unrealized_pnl)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (account["id"], ts, equity, 0.0, equity, 0.0, 0.0),
        )
    conn.commit()

    assert infer_overall_trend(conn, account["id"], current_equity=980.0, lookback=10) == "down"
    assert infer_overall_trend(conn, account["id"], current_equity=991.0, lookback=10) == "flat"


def test_infer_overall_trend_zero_first_equity_is_insufficient(conn) -> None:
    create_account(conn, "acct_zero", "Trend", 1000.0, "SPY")
    account = get_account(conn, "acct_zero")
    conn.execute(
        """
        INSERT INTO equity_snapshots (account_id, snapshot_time, cash, market_value, equity, realized_pnl, unrealized_pnl)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (account["id"], "2026-02-01T00:00:00Z", 0.0, 0.0, 0.0, 0.0, 0.0),
    )
    conn.execute(
        """
        INSERT INTO equity_snapshots (account_id, snapshot_time, cash, market_value, equity, realized_pnl, unrealized_pnl)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (account["id"], "2026-02-02T00:00:00Z", 10.0, 0.0, 10.0, 0.0, 0.0),
    )
    conn.commit()

    trend = infer_overall_trend(conn, account["id"], current_equity=20.0, lookback=10)
    assert trend == "insufficient-data"


def test_account_report_outputs_with_and_without_benchmark(conn, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    create_account(conn, "acct_report_out", "Trend", 1000.0, "SPY")
    account = get_account(conn, "acct_report_out")
    conn.execute(
        """
        INSERT INTO trades (account_id, ticker, side, qty, price, fee, trade_time, note)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (account["id"], "AAPL", "buy", 2, 100, 0, "2026-01-01T00:00:00Z", "entry"),
    )
    conn.commit()

    monkeypatch.setattr("trading.reporting.fetch_latest_prices", lambda _tickers: {"AAPL": 120.0})
    monkeypatch.setattr("trading.reporting.benchmark_stats", lambda *_args: (1050.0, 5.0))

    stats, positions = account_report(conn, "acct_report_out")
    out = capsys.readouterr().out

    assert stats["equity"] == pytest.approx(1040.0)
    assert positions == {"AAPL": 2.0}
    assert "Benchmark Equity: 1050.00" in out
    assert "Strategy Alpha vs Benchmark %: -1.00" in out
    assert "Open Positions:" in out

    monkeypatch.setattr("trading.reporting.benchmark_stats", lambda *_args: (None, None))
    account_report(conn, "acct_report_out")
    out2 = capsys.readouterr().out
    assert "Benchmark comparison: unavailable (price history not found)" in out2


def test_account_report_prints_leaps_fields(conn, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    create_account(
        conn,
        "acct_leaps",
        "Trend",
        5000.0,
        "SPY",
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
        profit_take_pct=30.0,
        max_loss_pct=20.0,
    )
    monkeypatch.setattr("trading.reporting.fetch_latest_prices", lambda _tickers: {})
    monkeypatch.setattr("trading.reporting.benchmark_stats", lambda *_args: (None, None))

    account_report(conn, "acct_leaps")
    out = capsys.readouterr().out
    assert "LEAPs Params:" in out
    assert "Options Filters:" in out
    assert "Options Risk:" in out


def test_compare_strategies_no_accounts_message(conn, capsys) -> None:
    compare_strategies(conn, lookback=5)
    out = capsys.readouterr().out
    assert "No paper accounts found." in out


def test_compare_strategies_outputs_summary_and_na_benchmark(conn, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    create_account(conn, "acct_cmp", "Trend", 1000.0, "SPY", descriptive_name="Compare")
    account = get_account(conn, "acct_cmp")
    conn.execute(
        """
        INSERT INTO trades (account_id, ticker, side, qty, price, fee, trade_time, note)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (account["id"], "AAPL", "buy", 1, 100, 0, "2026-01-01T00:00:00Z", "entry"),
    )
    conn.commit()

    monkeypatch.setattr("trading.reporting.fetch_latest_prices", lambda _tickers: {"AAPL": 101.0})
    monkeypatch.setattr("trading.reporting.benchmark_stats", lambda *_args: (None, None))

    compare_strategies(conn, lookback=5)
    out = capsys.readouterr().out
    assert "Per-strategy comparison:" in out
    assert "benchmark_equity=N/A benchmark_return=N/A alpha=N/A" in out
    assert "positions: AAPL:1.00" in out


def test_compare_strategies_truncates_positions_list(conn, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    create_account(conn, "acct_many", "Trend", 10000.0, "SPY", descriptive_name="Many")
    account = get_account(conn, "acct_many")

    tickers = ["AAPL", "AMZN", "GOOG", "META", "MSFT", "NVDA"]
    for i, ticker in enumerate(tickers):
        conn.execute(
            """
            INSERT INTO trades (account_id, ticker, side, qty, price, fee, trade_time, note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (account["id"], ticker, "buy", 1, 100 + i, 0, f"2026-01-01T00:00:0{i}Z", "entry"),
        )
    conn.commit()

    monkeypatch.setattr("trading.reporting.fetch_latest_prices", lambda symbols: {symbol: 110.0 for symbol in symbols})
    monkeypatch.setattr("trading.reporting.benchmark_stats", lambda *_args: (10100.0, 1.0))
    monkeypatch.setattr("trading.reporting.infer_overall_trend", lambda *_args, **_kwargs: "up")

    compare_strategies(conn, lookback=5)
    out = capsys.readouterr().out
    assert "positions: AAPL:1.00, AMZN:1.00, GOOG:1.00, META:1.00, MSFT:1.00, ..." in out


def test_snapshot_account_inserts_and_defaults_time(conn, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    create_account(conn, "acct_snap", "Trend", 1000.0, "SPY")
    monkeypatch.setattr(
        reporting,
        "account_report",
        lambda _conn, _name: (
            {
                "cash": 900.0,
                "market_value": 150.0,
                "equity": 1050.0,
                "realized_pnl": 20.0,
                "unrealized_pnl": 30.0,
                "strategy_return_pct": 5.0,
            },
            {"AAPL": 1.0},
        ),
    )
    monkeypatch.setattr(reporting, "utc_now_iso", lambda: "2099-01-01T00:00:00Z")

    snapshot_account(conn, "acct_snap", snapshot_time=None)
    out = capsys.readouterr().out
    assert "Snapshot saved." in out

    account = get_account(conn, "acct_snap")
    row = conn.execute(
        "SELECT snapshot_time, equity FROM equity_snapshots WHERE account_id = ?",
        (account["id"],),
    ).fetchone()
    assert row is not None
    assert row["snapshot_time"] == "2099-01-01T00:00:00Z"
    assert float(row["equity"]) == pytest.approx(1050.0)


def test_show_snapshots_empty_and_rows(conn, capsys) -> None:
    create_account(conn, "acct_show", "Trend", 1000.0, "SPY")

    show_snapshots(conn, "acct_show", limit=5)
    out_empty = capsys.readouterr().out
    assert "No snapshots found." in out_empty

    account = get_account(conn, "acct_show")
    conn.execute(
        """
        INSERT INTO equity_snapshots (account_id, snapshot_time, cash, market_value, equity, realized_pnl, unrealized_pnl)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (account["id"], "2026-03-01T00:00:00Z", 900.0, 100.0, 1000.0, 10.0, 15.0),
    )
    conn.commit()

    show_snapshots(conn, "acct_show", limit=5)
    out_rows = capsys.readouterr().out
    assert "Snapshot history (latest 5) for acct_show:" in out_rows
    assert "equity=1000.00" in out_rows
