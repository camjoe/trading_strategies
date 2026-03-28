import pytest

from trading import accounting
from trading.accounting import compute_account_state, load_trades, record_trade
from trading.accounts import create_account, get_account


class TestComputeAccountState:
    def test_buy_sell_realized_pnl(self) -> None:
        trades = [
            {"ticker": "AAPL", "side": "buy", "qty": 10, "price": 100, "fee": 1},
            {"ticker": "AAPL", "side": "sell", "qty": 4, "price": 110, "fee": 1},
        ]

        state = compute_account_state(initial_cash=1000.0, trades=trades)

        assert state.positions == {"AAPL": 6.0}
        assert state.avg_cost["AAPL"] == pytest.approx(100.1)
        assert state.cash == pytest.approx(438.0)
        assert state.realized_pnl == pytest.approx(38.6)


    def test_rejects_non_positive_qty(self) -> None:
        with pytest.raises(ValueError, match="Trade quantity must be > 0"):
            compute_account_state(
                initial_cash=1000.0,
                trades=[{"ticker": "AAPL", "side": "buy", "qty": 0, "price": 100, "fee": 1}],
            )

    def test_rejects_non_positive_price(self) -> None:
        with pytest.raises(ValueError, match="Trade price must be > 0"):
            compute_account_state(
                initial_cash=1000.0,
                trades=[{"ticker": "AAPL", "side": "buy", "qty": 1, "price": 0, "fee": 1}],
            )


    def test_rejects_invalid_side(self) -> None:
        with pytest.raises(ValueError, match="Unsupported side: hold"):
            compute_account_state(
                initial_cash=1000.0,
                trades=[{"ticker": "AAPL", "side": "hold", "qty": 1, "price": 100, "fee": 1}],
            )

    def test_rejects_sell_above_holdings(self) -> None:
        with pytest.raises(ValueError, match="Invalid sell for AAPL"):
            compute_account_state(
                initial_cash=1000.0,
                trades=[{"ticker": "AAPL", "side": "sell", "qty": 1, "price": 100, "fee": 1}],
            )

    def test_sell_all_removes_position_and_avg_cost(self) -> None:
        state = compute_account_state(
            initial_cash=1000.0,
            trades=[
                {"ticker": "AAPL", "side": "buy", "qty": 2, "price": 100, "fee": 0},
                {"ticker": "AAPL", "side": "sell", "qty": 2, "price": 110, "fee": 0},
            ],
        )

        assert state.positions == {}
        assert state.avg_cost == {}
        assert state.realized_pnl == pytest.approx(20.0)
        assert state.cash == pytest.approx(1020.0)


    def test_multiple_buys_updates_weighted_avg_cost(self) -> None:
        state = compute_account_state(
            initial_cash=1000.0,
            trades=[
                {"ticker": "AAPL", "side": "buy", "qty": 2, "price": 100, "fee": 0},
                {"ticker": "AAPL", "side": "buy", "qty": 1, "price": 130, "fee": 1},
            ],
        )

        assert state.positions == {"AAPL": 3.0}
        assert state.avg_cost["AAPL"] == pytest.approx((200.0 + 131.0) / 3.0)
        assert state.cash == pytest.approx(669.0)


class TestRecordTradeAndLoadTrades:
    def test_rejects_insufficient_cash(self, conn) -> None:
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


    def test_roundtrip(self, conn) -> None:
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
        rows = conn.execute(
            "SELECT ticker, side, qty, price, note FROM trades WHERE account_id = ?",
            (account["id"],),
        ).fetchall()

        assert len(rows) == 1
        row = rows[0]
        assert row["ticker"] == "NVDA"
        assert row["side"] == "buy"
        assert float(row["qty"]) == pytest.approx(3.0)
        assert float(row["price"]) == pytest.approx(100.0)
        assert row["note"] == "entry"


    def test_rejects_invalid_side(self, conn) -> None:
        create_account(conn, "acct_bad_side", "Trend", 1000.0, "SPY")

        with pytest.raises(ValueError, match="side must be one of: buy, sell"):
            record_trade(
                conn,
                account_name="acct_bad_side",
                side="hold",
                ticker="MSFT",
                qty=1,
                price=100,
                fee=0,
                trade_time="2026-01-01T00:00:00Z",
                note=None,
            )


    def test_sell_does_not_require_cash(self, conn) -> None:
        create_account(conn, "acct_sell", "Trend", 0.01, "SPY")

        record_trade(
            conn,
            account_name="acct_sell",
            side="buy",
            ticker="AAPL",
            qty=1,
            price=0.01,
            fee=0,
            trade_time="2026-01-01T00:00:00Z",
            note="entry",
        )

        record_trade(
            conn,
            account_name="acct_sell",
            side="sell",
            ticker="AAPL",
            qty=1,
            price=0.02,
            fee=0,
            trade_time="2026-01-01T00:00:01Z",
            note="exit",
        )

        account = get_account(conn, "acct_sell")
        rows = conn.execute("SELECT side FROM trades WHERE account_id = ? ORDER BY id", (account["id"],)).fetchall()
        assert [row["side"] for row in rows] == ["buy", "sell"]


    def test_uses_default_trade_time_when_missing(self, conn, monkeypatch: pytest.MonkeyPatch) -> None:
        create_account(conn, "acct_default_time", "Trend", 1000.0, "SPY")
        monkeypatch.setattr(accounting, "utc_now_iso", lambda: "2099-01-01T00:00:00Z")

        record_trade(
            conn,
            account_name="acct_default_time",
            side="buy",
            ticker="MSFT",
            qty=1,
            price=10,
            fee=0,
            trade_time=None,
            note=None,
        )

        account = get_account(conn, "acct_default_time")
        row = conn.execute("SELECT trade_time FROM trades WHERE account_id = ?", (account["id"],)).fetchone()
        assert row is not None
        assert row["trade_time"] == "2099-01-01T00:00:00Z"


    def test_normalizes_side_and_ticker(self, conn) -> None:
        create_account(conn, "acct_norm_order", "Trend", 1000.0, "SPY")

        record_trade(
            conn,
            account_name="acct_norm_order",
            side=" BUY ",
            ticker=" msft ",
            qty=1,
            price=10,
            fee=0,
            trade_time="2026-01-01T00:00:00Z",
            note=None,
        )

        account = get_account(conn, "acct_norm_order")
        row = conn.execute(
            "SELECT side, ticker FROM trades WHERE account_id = ?",
            (account["id"],),
        ).fetchone()
        assert row is not None
        assert row["side"] == "buy"
        assert row["ticker"] == "MSFT"


    def test_load_trades_orders_by_trade_time_then_id(self, conn) -> None:
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

        rows = load_trades(conn, account["id"])
        assert [row["ticker"] for row in rows] == ["AAPL", "MSFT", "GOOG"]
