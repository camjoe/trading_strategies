from __future__ import annotations

import pytest

from trading.models import AccountInsert
from trading.repositories.accounts import AccountRepository
from tests.support.repositories import insert_repository_account
from tests.support.strategies import ensure_strategy_id_for_label


def _make_account_insert(**overrides: object) -> AccountInsert:
    values: dict[str, object] = {
        "name": "acct_a",
        "account_kind": "managed",
        "initial_cash": 1000.0,
        "created_at": "2026-01-01T00:00:00",
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
        row = AccountRepository(conn).fetch_by_name("acct_a")
        assert row is not None
        assert row["name"] == "acct_a"

    def test_returns_none_for_missing_account(self, conn) -> None:
        assert AccountRepository(conn).fetch_by_name("ghost") is None


class TestInsertAccount:
    def test_round_trip_stores_all_fields(self, conn) -> None:
        AccountRepository(conn).insert(
            _make_account_insert(
                name="full_acct",
                account_kind="local",
                initial_cash=5000.0,
                created_at="2026-03-01T10:00:00",
                benchmark_ticker="QQQ",
                descriptive_name="Full Account",
            ),
        )
        row = AccountRepository(conn).fetch_by_name("full_acct")
        assert row is not None
        assert row["account_kind"] == "local"
        assert float(row["initial_cash"]) == pytest.approx(5000.0)
        assert row["benchmark_ticker"] == "QQQ"
        assert row["descriptive_name"] == "Full Account"


class TestUpdateAccountBenchmark:
    def test_updates_benchmark_ticker(self, conn) -> None:
        _insert(conn, "bench_acct")
        repo = AccountRepository(conn)
        row = repo.fetch_by_name("bench_acct")
        repo.update_benchmark(account_id=row["id"], benchmark_ticker="QQQ")
        updated = repo.fetch_by_name("bench_acct")
        assert updated["benchmark_ticker"] == "QQQ"


class TestFetchAccountListingRows:
    def test_returns_all_accounts_ordered_by_strategy_then_name(self, conn) -> None:
        _insert(conn, "z_acct")
        _insert(conn, "a_acct")
        _insert(conn, "m_acct")
        rows = AccountRepository(conn).fetch_listing()
        names = [r["name"] for r in rows]
        assert names == ["a_acct", "m_acct", "z_acct"]

    def test_empty_table_returns_empty_list(self, conn) -> None:
        assert AccountRepository(conn).fetch_listing() == []


class TestFetchAccountRows:
    def test_returns_all_accounts_ordered_by_name(self, conn) -> None:
        _insert(conn, "keep_me")
        AccountRepository(conn).insert(
            _make_account_insert(name="local_acct", descriptive_name="local_acct", account_kind="local")
        )
        names = [r["name"] for r in AccountRepository(conn).fetch_all()]
        assert names == ["keep_me", "local_acct"]

    def test_ordered_by_name(self, conn) -> None:
        _insert(conn, "bravo")
        _insert(conn, "alpha")
        AccountRepository(conn).insert(
            _make_account_insert(name="skip_me", descriptive_name="skip_me", account_kind="local")
        )
        rows = AccountRepository(conn).fetch_all()
        names = [r["name"] for r in rows]
        assert names == ["alpha", "bravo", "skip_me"]


class TestUpdateAccountFields:
    def test_updates_single_field(self, conn) -> None:
        _insert(conn, "upd_acct")
        repo = AccountRepository(conn)
        row = repo.fetch_by_name("upd_acct")
        repo.update(account_id=row["id"], updates=["descriptive_name = ?"], params=["Renamed"])
        updated = repo.fetch_by_name("upd_acct")
        assert updated["descriptive_name"] == "Renamed"

    def test_updates_multiple_fields(self, conn) -> None:
        _insert(conn, "multi_upd")
        repo = AccountRepository(conn)
        row = repo.fetch_by_name("multi_upd")
        repo.update(
            account_id=row["id"],
            updates=["descriptive_name = ?", "account_kind = ?"],
            params=["Multi", "local"],
        )
        updated = repo.fetch_by_name("multi_upd")
        assert updated["descriptive_name"] == "Multi"
        assert updated["account_kind"] == "local"


class TestFetchAllAccountNames:
    def test_returns_sorted_names(self, conn) -> None:
        _insert(conn, "zulu")
        _insert(conn, "alpha")
        _insert(conn, "mike")
        assert AccountRepository(conn).fetch_names() == ["alpha", "mike", "zulu"]

    def test_empty_table_returns_empty(self, conn) -> None:
        assert AccountRepository(conn).fetch_names() == []


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


def _insert_trade(conn, *, account_id: int) -> None:
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
        _insert_trade(conn, account_id=acct_id)
        run_id = _insert_backtest_run(conn, account_id=acct_id)

        repo = AccountRepository(conn)
        deleted = repo.delete_by_name("count_acct")

        assert deleted is not None
        assert deleted.name == "count_acct"
        assert conn.execute("SELECT id FROM accounts WHERE id = ?", (acct_id,)).fetchone() is None
        assert conn.execute("SELECT id FROM backtest_runs WHERE id = ?", (run_id,)).fetchone() is None
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []

    def test_does_not_remove_other_accounts(self, conn) -> None:
        _account_id(conn, "del_a")
        acct_b = _account_id(conn, "del_b")
        AccountRepository(conn).delete_by_name("del_a")
        row = conn.execute("SELECT id FROM accounts WHERE id = ?", (acct_b,)).fetchone()
        assert row is not None

    def test_returns_none_for_missing_account(self, conn) -> None:
        assert AccountRepository(conn).delete_by_name("missing") is None
