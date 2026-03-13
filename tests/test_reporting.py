import pytest

from trading.accounts import create_account, get_account
from trading.reporting import build_account_stats, infer_overall_trend


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
