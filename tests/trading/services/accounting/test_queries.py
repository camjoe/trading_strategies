from trading.services.accounting import list_account_trades
from trading.services.accounts import create_account, get_account


def test_list_account_trades_orders_by_trade_time_then_id(conn) -> None:
    create_account(conn, "acct_order", "Trend", 1000.0, "SPY")
    account = get_account(conn, "acct_order")

    conn.execute(
        "INSERT INTO trades (account_id, ticker, side, qty, price, fee, trade_time, note) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (account["id"], "MSFT", "buy", 1.0, 10.0, 0.0, "2026-01-01T00:00:01Z", "second"),
    )
    conn.execute(
        "INSERT INTO trades (account_id, ticker, side, qty, price, fee, trade_time, note) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (account["id"], "AAPL", "buy", 1.0, 10.0, 0.0, "2026-01-01T00:00:00Z", "first"),
    )
    conn.execute(
        "INSERT INTO trades (account_id, ticker, side, qty, price, fee, trade_time, note) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (account["id"], "GOOG", "buy", 1.0, 10.0, 0.0, "2026-01-01T00:00:01Z", "third"),
    )
    conn.commit()

    rows = list_account_trades(conn, account["id"])
    assert [row["ticker"] for row in rows] == ["AAPL", "MSFT", "GOOG"]
