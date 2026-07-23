import pytest

import trading.services.execution.ledger.mutations as accounting_mutations
from common.time import utc_now_iso
from trading.repositories.books import BookRepository
from trading.services.accounts import create_account, get_account
from trading.services.books.book_assignments import get_default_book
from trading.services.execution.ledger import list_account_trades, record_trade
from trading.services.operational_settings import set_runtime_throttle_settings


class TestRecordTrade:
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
        rows = list_account_trades(conn, account["id"])

        assert len(rows) == 1
        row = rows[0]
        assert row["ticker"] == "NVDA"
        assert row["side"] == "buy"
        assert float(row["qty"]) == pytest.approx(3.0)
        assert float(row["price"]) == pytest.approx(100.0)

        # The fill was applied to the default book (revision 0006).
        book = get_default_book(conn, account_id=account.id)
        assert book is not None
        assert book.current_cash == pytest.approx(700.0)

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

    def test_rejects_oversell(self, conn) -> None:
        create_account(conn, "acct_oversell", "Trend", 1000.0, "SPY")

        with pytest.raises(ValueError, match="Invalid sell"):
            record_trade(
                conn,
                account_name="acct_oversell",
                side="sell",
                ticker="AAPL",
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
        rows = list_account_trades(conn, account["id"])
        assert [row["side"] for row in rows] == ["buy", "sell"]

    def test_cash_ticker_records_ledger_deposit(self, conn) -> None:
        create_account(conn, "acct_deposit", "Trend", 100.0, "SPY")

        record_trade(
            conn,
            account_name="acct_deposit",
            side="buy",
            ticker="CASH",
            qty=250,
            price=1.0,
            fee=0,
            trade_time="2026-01-01T00:00:00Z",
            note="deposit",
        )

        account = get_account(conn, "acct_deposit")
        book = get_default_book(conn, account_id=account.id)
        assert book is not None
        assert book.current_cash == pytest.approx(350.0)
        from trading.services.execution.ledger import load_account_state

        state = load_account_state(conn, account_id=account.id, initial_cash=account.initial_cash)
        assert state.total_deposited == pytest.approx(250.0)
        assert state.cash == pytest.approx(350.0)

    def test_cash_ticker_rolls_back_ledger_when_balance_update_fails(self, conn, monkeypatch) -> None:
        create_account(conn, "acct_cash_rollback", "Trend", 100.0, "SPY")
        account = get_account(conn, "acct_cash_rollback")
        book = get_default_book(conn, account_id=account.id)
        assert book is not None

        def fail_balance_update(*args, **kwargs) -> None:
            raise RuntimeError("balance update failed")

        monkeypatch.setattr(BookRepository, "update_balances", fail_balance_update)

        with pytest.raises(RuntimeError, match="balance update failed"):
            record_trade(
                conn,
                account_name="acct_cash_rollback",
                side="buy",
                ticker="CASH",
                qty=250,
                price=1.0,
                fee=0,
                trade_time="2026-01-01T00:00:00Z",
                note="deposit",
            )

        ledger_count = conn.execute("SELECT COUNT(*) FROM ledger WHERE book_id = ?", (book.id,)).fetchone()[0]
        assert ledger_count == 0
        unchanged = get_default_book(conn, account_id=account.id)
        assert unchanged is not None
        assert unchanged.current_cash == pytest.approx(100.0)

    def test_uses_default_trade_time_when_missing(self, conn, monkeypatch: pytest.MonkeyPatch) -> None:
        create_account(conn, "acct_default_time", "Trend", 1000.0, "SPY")
        monkeypatch.setattr(accounting_mutations, "utc_now_iso", lambda: "2099-01-01T00:00:00Z")

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
        row = list_account_trades(conn, account["id"])[0]
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
        row = list_account_trades(conn, account["id"])[0]
        assert row["side"] == "buy"
        assert row["ticker"] == "MSFT"

    def test_global_runtime_trade_settings_do_not_block_manual_recording(self, conn) -> None:
        create_account(conn, "acct_global_settings_manual", "Trend", 1000.0, "SPY")
        set_runtime_throttle_settings(
            conn,
            runtime_max_trades_per_day=1,
            runtime_max_trades_per_minute=1,
            updated_at=utc_now_iso(),
        )

        record_trade(
            conn,
            account_name="acct_global_settings_manual",
            side="buy",
            ticker="AAPL",
            qty=1,
            price=10,
            fee=0,
            trade_time="2026-01-01T00:00:00Z",
            note="manual",
        )
        record_trade(
            conn,
            account_name="acct_global_settings_manual",
            side="buy",
            ticker="MSFT",
            qty=1,
            price=10,
            fee=0,
            trade_time="2026-01-01T00:00:01Z",
            note="manual",
        )

        account = get_account(conn, "acct_global_settings_manual")
        assert len(list_account_trades(conn, account["id"])) == 2
