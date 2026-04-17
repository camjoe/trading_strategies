from __future__ import annotations

from trading.services.accounts_service import create_account
from trading.repositories.trades_repository import (
    count_trades_between,
    fetch_trades_for_account,
    insert_trade,
)


def _account_id(conn, name: str = "trade_acct") -> int:
    create_account(conn, name, "Trend", 5000.0, "SPY")
    row = conn.execute("SELECT id FROM accounts WHERE name = ?", (name,)).fetchone()
    return int(row["id"])


class TestInsertTrade:
    def test_inserted_trade_is_fetchable(self, conn) -> None:
        acct_id = _account_id(conn)
        insert_trade(
            conn,
            account_id=acct_id,
            ticker="AAPL",
            side="buy",
            qty=10.0,
            price=150.0,
            fee=0.0,
            trade_time="2026-01-01T10:00:00",
            note=None,
        )
        rows = fetch_trades_for_account(conn, account_id=acct_id)
        assert len(rows) == 1
        assert rows[0]["ticker"] == "AAPL"
        assert rows[0]["side"] == "buy"
        assert float(rows[0]["qty"]) == 10.0
        assert float(rows[0]["price"]) == 150.0

    def test_note_stored_and_retrieved(self, conn) -> None:
        acct_id = _account_id(conn)
        insert_trade(
            conn,
            account_id=acct_id,
            ticker="MSFT",
            side="sell",
            qty=5.0,
            price=300.0,
            fee=1.0,
            trade_time="2026-01-02T11:00:00",
            note="forced sell",
        )
        # fetch_trades_for_account doesn't project `note`; query directly
        row = conn.execute(
            "SELECT note FROM trades WHERE account_id = ?", (acct_id,)
        ).fetchone()
        assert row["note"] == "forced sell"


class TestFetchTradesForAccount:
    def test_empty_when_no_trades(self, conn) -> None:
        acct_id = _account_id(conn)
        assert fetch_trades_for_account(conn, account_id=acct_id) == []

    def test_only_returns_trades_for_requested_account(self, conn) -> None:
        acct_a = _account_id(conn, "acct_a")
        acct_b = _account_id(conn, "acct_b")
        insert_trade(
            conn,
            account_id=acct_a,
            ticker="AAPL",
            side="buy",
            qty=1.0,
            price=100.0,
            fee=0.0,
            trade_time="2026-01-01T09:00:00",
            note=None,
        )
        insert_trade(
            conn,
            account_id=acct_b,
            ticker="MSFT",
            side="buy",
            qty=2.0,
            price=200.0,
            fee=0.0,
            trade_time="2026-01-01T09:00:00",
            note=None,
        )
        rows_a = fetch_trades_for_account(conn, account_id=acct_a)
        assert len(rows_a) == 1
        assert rows_a[0]["ticker"] == "AAPL"

    def test_ordered_by_trade_time_then_id(self, conn) -> None:
        acct_id = _account_id(conn)
        insert_trade(
            conn,
            account_id=acct_id,
            ticker="LATER",
            side="buy",
            qty=1.0,
            price=10.0,
            fee=0.0,
            trade_time="2026-01-02T00:00:00",
            note=None,
        )
        insert_trade(
            conn,
            account_id=acct_id,
            ticker="EARLIER",
            side="buy",
            qty=1.0,
            price=10.0,
            fee=0.0,
            trade_time="2026-01-01T00:00:00",
            note=None,
        )
        rows = fetch_trades_for_account(conn, account_id=acct_id)
        assert rows[0]["ticker"] == "EARLIER"
        assert rows[1]["ticker"] == "LATER"


class TestCountTradesBetween:
    def test_counts_only_rows_inside_window(self, conn) -> None:
        acct_id = _account_id(conn)
        insert_trade(
            conn,
            account_id=acct_id,
            ticker="AAPL",
            side="buy",
            qty=1.0,
            price=100.0,
            fee=0.0,
            trade_time="2026-01-01T00:00:00Z",
            note=None,
        )
        insert_trade(
            conn,
            account_id=acct_id,
            ticker="MSFT",
            side="buy",
            qty=1.0,
            price=100.0,
            fee=0.0,
            trade_time="2026-01-01T00:01:00Z",
            note=None,
        )

        assert count_trades_between(
            conn,
            "2026-01-01T00:00:30Z",
            "2026-01-01T00:01:30Z",
        ) == 1
