from __future__ import annotations

import pytest

from tests.support.repositories import insert_repository_account
from tests.support.strategies import ensure_strategy_id_for_label
from trading.models import AccountInsert
from trading.repositories.accounts import AccountRepository


def _make_account_insert(**overrides: object) -> AccountInsert:
    values: dict[str, object] = {
        "name": "acct_a",
        "initial_cash": 1000.0,
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T00:00:00",
        "benchmark_ticker": "SPY",
        "descriptive_name": "acct_a",
    }
    values.update(overrides)
    return AccountInsert(**values)


def _insert(conn, name: str) -> None:
    AccountRepository(conn).insert(_make_account_insert(name=name, descriptive_name=name))


class TestFetchAccountByName:
    def test_returns_row_for_existing_account(self, conn) -> None:
        _insert(conn, "acct_a")
        row = AccountRepository(conn).fetch_by_name(account_name="acct_a")
        assert row is not None
        assert row["name"] == "acct_a"

    def test_returns_none_for_missing_account(self, conn) -> None:
        assert AccountRepository(conn).fetch_by_name(account_name="ghost") is None


class TestFetchAccountById:
    def test_returns_row_for_existing_account(self, conn) -> None:
        _insert(conn, "acct_a")
        repo = AccountRepository(conn)
        existing = repo.fetch_by_name(account_name="acct_a")
        assert existing is not None
        row = repo.fetch_by_id(account_id=existing.id)
        assert row is not None
        assert row["name"] == "acct_a"

    def test_returns_none_for_missing_account(self, conn) -> None:
        assert AccountRepository(conn).fetch_by_id(account_id=999999) is None


class TestInsertAccount:
    def test_round_trip_stores_all_fields(self, conn) -> None:
        AccountRepository(conn).insert(
            _make_account_insert(
                name="full_acct",
                initial_cash=5000.0,
                created_at="2026-03-01T10:00:00",
                benchmark_ticker="QQQ",
                descriptive_name="Full Account",
            ),
        )
        row = AccountRepository(conn).fetch_by_name(account_name="full_acct")
        assert row is not None
        assert float(row["initial_cash"]) == pytest.approx(5000.0)
        assert row["benchmark_ticker"] == "QQQ"
        assert row["descriptive_name"] == "Full Account"


class TestUpdateAccountBenchmark:
    def test_updates_benchmark_ticker(self, conn) -> None:
        _insert(conn, "bench_acct")
        repo = AccountRepository(conn)
        row = repo.fetch_by_name(account_name="bench_acct")
        repo.update(account_id=row["id"], values={"benchmark_ticker": "QQQ"}, updated_at="2026-02-01T00:00:00")
        updated = repo.fetch_by_name(account_name="bench_acct")
        assert updated["benchmark_ticker"] == "QQQ"
        stamped = conn.execute("SELECT updated_at FROM accounts WHERE id = ?", (row["id"],)).fetchone()
        assert stamped["updated_at"] == "2026-02-01T00:00:00"


class TestFetchAccountRows:
    def test_empty_table_returns_empty_list(self, conn) -> None:
        assert AccountRepository(conn).fetch_all() == []

    def test_returns_all_accounts_ordered_by_name(self, conn) -> None:
        _insert(conn, "keep_me")
        AccountRepository(conn).insert(_make_account_insert(name="second_acct", descriptive_name="second_acct"))
        names = [r["name"] for r in AccountRepository(conn).fetch_all()]
        assert names == ["keep_me", "second_acct"]

    def test_ordered_by_name(self, conn) -> None:
        _insert(conn, "bravo")
        _insert(conn, "alpha")
        AccountRepository(conn).insert(_make_account_insert(name="skip_me", descriptive_name="skip_me"))
        rows = AccountRepository(conn).fetch_all()
        names = [r["name"] for r in rows]
        assert names == ["alpha", "bravo", "skip_me"]


class TestUpdateAccountFields:
    def test_updates_single_field(self, conn) -> None:
        _insert(conn, "upd_acct")
        repo = AccountRepository(conn)
        row = repo.fetch_by_name(account_name="upd_acct")
        repo.update(
            account_id=row["id"],
            values={"descriptive_name": "Renamed"},
            updated_at="2026-02-01T00:00:00",
        )
        updated = repo.fetch_by_name(account_name="upd_acct")
        assert updated["descriptive_name"] == "Renamed"
        stamped = conn.execute("SELECT updated_at FROM accounts WHERE id = ?", (row["id"],)).fetchone()
        assert stamped["updated_at"] == "2026-02-01T00:00:00"

    def test_updates_multiple_fields(self, conn) -> None:
        _insert(conn, "multi_upd")
        repo = AccountRepository(conn)
        row = repo.fetch_by_name(account_name="multi_upd")
        repo.update(
            account_id=row["id"],
            values={"descriptive_name": "Multi", "benchmark_ticker": "QQQ"},
            updated_at="2026-02-01T00:00:00",
        )
        updated = repo.fetch_by_name(account_name="multi_upd")
        assert updated["descriptive_name"] == "Multi"
        assert updated["benchmark_ticker"] == "QQQ"


def _account_id(conn, name: str = "count_acct") -> int:
    return insert_repository_account(conn, name=name)


def _insert_backtest_run(conn, *, account_id: int, strategy_name: str = "trend") -> int:
    cursor = conn.execute(
        "INSERT INTO backtest_runs (account_id, strategy_id, start_date, end_date, created_at) VALUES (?,?,?,?,?)",
        (
            account_id,
            ensure_strategy_id_for_label(conn, strategy_name),
            "2026-01-01",
            "2026-06-01",
            "2026-01-01T00:00:00Z",
        ),
    )
    conn.commit()
    return cursor.lastrowid


def _persist_trade(conn, *, account_id: int) -> None:
    from tests.support.fills import seed_fill_event

    seed_fill_event(
        conn,
        account_id=account_id,
        ticker="AAPL",
        side="buy",
        qty=1.0,
        price=100.0,
        trade_time="2026-01-01T10:00:00Z",
    )


class TestDeleteByName:
    def test_removes_account_and_cascades_owned_rows(self, conn) -> None:
        acct_id = _account_id(conn)
        _persist_trade(conn, account_id=acct_id)
        run_id = _insert_backtest_run(conn, account_id=acct_id)

        repo = AccountRepository(conn)
        deleted = repo.delete_by_name(account_name="count_acct")

        assert deleted is not None
        assert deleted.name == "count_acct"
        assert conn.execute("SELECT id FROM accounts WHERE id = ?", (acct_id,)).fetchone() is None
        assert conn.execute("SELECT id FROM backtest_runs WHERE id = ?", (run_id,)).fetchone() is None
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []

    def test_does_not_remove_other_accounts(self, conn) -> None:
        _account_id(conn, "del_a")
        acct_b = _account_id(conn, "del_b")
        AccountRepository(conn).delete_by_name(account_name="del_a")
        row = conn.execute("SELECT id FROM accounts WHERE id = ?", (acct_b,)).fetchone()
        assert row is not None

    def test_returns_none_for_missing_account(self, conn) -> None:
        assert AccountRepository(conn).delete_by_name(account_name="missing") is None
