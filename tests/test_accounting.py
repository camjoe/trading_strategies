import pytest

from trading.accounting import compute_account_state, record_trade
from trading.accounts import create_account, get_account


def test_compute_account_state_buy_sell_realized_pnl() -> None:
    trades = [
        {"ticker": "AAPL", "side": "buy", "qty": 10, "price": 100, "fee": 1},
        {"ticker": "AAPL", "side": "sell", "qty": 4, "price": 110, "fee": 1},
    ]

    state = compute_account_state(initial_cash=1000.0, trades=trades)

    assert state.positions == {"AAPL": 6.0}
    assert state.avg_cost["AAPL"] == pytest.approx(100.1)
    assert state.cash == pytest.approx(438.0)
    assert state.realized_pnl == pytest.approx(38.6)


def test_record_trade_rejects_insufficient_cash(conn) -> None:
    create_account(conn, "acct_cash", "Trend", 100.0, "SPY")

    with pytest.raises(ValueError, match="Insufficient cash"):
        record_trade(
            conn,
            account_name="acct_cash",
            side="buy",
            ticker="MSFT",
            qty=2,
            price=60,
            fee=0,
            trade_time="2026-01-01T00:00:00Z",
            note=None,
        )


def test_record_trade_roundtrip(conn) -> None:
    create_account(conn, "acct_roundtrip", "Trend", 1000.0, "SPY")

    record_trade(
        conn,
        account_name="acct_roundtrip",
        side="buy",
        ticker="NVDA",
        qty=3,
        price=100,
        fee=0,
        trade_time="2026-01-01T00:00:00Z",
        note="entry",
    )

    account = get_account(conn, "acct_roundtrip")
    rows = conn.execute("SELECT ticker, side, qty, price, note FROM trades WHERE account_id = ?", (account["id"],)).fetchall()

    assert len(rows) == 1
    row = rows[0]
    assert row["ticker"] == "NVDA"
    assert row["side"] == "buy"
    assert float(row["qty"]) == pytest.approx(3.0)
    assert float(row["price"]) == pytest.approx(100.0)
    assert row["note"] == "entry"
