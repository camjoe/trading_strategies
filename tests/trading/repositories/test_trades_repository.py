from __future__ import annotations

from trading.repositories.trades import TradeRepository
from tests.support.repositories import insert_repository_account


def _account_id(conn, name: str = "trade_acct") -> int:
    return insert_repository_account(conn, name=name)


def _insert(conn, account_id: int, *, ticker: str = "AAPL", trade_time: str) -> None:
    TradeRepository(conn).insert(
        account_id=account_id,
        ticker=ticker,
        side="buy",
        qty=1.0,
        price=100.0,
        fee=0.0,
        trade_time=trade_time,
        note=None,
    )


class TestInsert:
    def test_inserted_trade_is_fetchable(self, conn) -> None:
        acct_id = _account_id(conn)
        repo = TradeRepository(conn)
        repo.insert(
            account_id=acct_id,
            ticker="AAPL",
            side="buy",
            qty=10.0,
            price=150.0,
            fee=0.0,
            trade_time="2026-01-01T10:00:00",
            note=None,
        )
        rows = repo.fetch_for_account(account_id=acct_id)
        assert len(rows) == 1
        assert rows[0]["ticker"] == "AAPL"
        assert rows[0]["side"] == "buy"
        assert float(rows[0]["qty"]) == 10.0
        assert float(rows[0]["price"]) == 150.0

    def test_note_stored_and_retrieved(self, conn) -> None:
        acct_id = _account_id(conn)
        TradeRepository(conn).insert(
            account_id=acct_id,
            ticker="MSFT",
            side="sell",
            qty=5.0,
            price=300.0,
            fee=1.0,
            trade_time="2026-01-02T11:00:00",
            note="forced sell",
        )
        row = conn.execute("SELECT note FROM trades WHERE account_id = ?", (acct_id,)).fetchone()
        assert row["note"] == "forced sell"


class TestFetchForAccount:
    def test_empty_when_no_trades(self, conn) -> None:
        acct_id = _account_id(conn)
        assert TradeRepository(conn).fetch_for_account(account_id=acct_id) == []

    def test_only_returns_trades_for_requested_account(self, conn) -> None:
        acct_a = _account_id(conn, "acct_a")
        acct_b = _account_id(conn, "acct_b")
        _insert(conn, acct_a, ticker="AAPL", trade_time="2026-01-01T09:00:00")
        _insert(conn, acct_b, ticker="MSFT", trade_time="2026-01-01T09:00:00")
        rows_a = TradeRepository(conn).fetch_for_account(account_id=acct_a)
        assert len(rows_a) == 1
        assert rows_a[0]["ticker"] == "AAPL"

    def test_ordered_by_trade_time_then_id(self, conn) -> None:
        acct_id = _account_id(conn)
        _insert(conn, acct_id, ticker="LATER", trade_time="2026-01-02T00:00:00")
        _insert(conn, acct_id, ticker="EARLIER", trade_time="2026-01-01T00:00:00")
        rows = TradeRepository(conn).fetch_for_account(account_id=acct_id)
        assert rows[0]["ticker"] == "EARLIER"
        assert rows[1]["ticker"] == "LATER"


class TestFetchCountBetween:
    def test_counts_only_rows_inside_window(self, conn) -> None:
        acct_id = _account_id(conn)
        repo = TradeRepository(conn)
        repo.insert(
            account_id=acct_id,
            ticker="AAPL",
            side="buy",
            qty=1.0,
            price=100.0,
            fee=0.0,
            trade_time="2026-01-01T00:00:00Z",
            note=None,
        )
        repo.insert(
            account_id=acct_id,
            ticker="MSFT",
            side="buy",
            qty=1.0,
            price=100.0,
            fee=0.0,
            trade_time="2026-01-01T00:01:00Z",
            note=None,
        )

        assert repo.fetch_count_between(
            start_iso="2026-01-01T00:00:30Z",
            end_iso="2026-01-01T00:01:30Z",
        ) == 1
