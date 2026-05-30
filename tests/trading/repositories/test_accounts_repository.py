from __future__ import annotations

import pytest

from trading.models import AccountInsert
from trading.repositories.accounts import AccountRepository


def _make_account_insert(**overrides: object) -> AccountInsert:
    values: dict[str, object] = {
        "name": "acct_a",
        "account_kind": "managed",
        "strategy": "Trend",
        "initial_cash": 1000.0,
        "created_at": "2026-01-01T00:00:00",
        "benchmark_ticker": "SPY",
        "descriptive_name": "acct_a",
        "goal_min_return_pct": None,
        "goal_max_return_pct": None,
        "goal_period": "monthly",
        "learning_enabled": 0,
        "risk_policy": "none",
        "stop_loss_pct": None,
        "take_profit_pct": None,
        "trade_size_pct": 10.0,
        "max_position_pct": 20.0,
        "instrument_mode": "equity",
        "option_strike_offset_pct": None,
        "option_min_dte": None,
        "option_max_dte": None,
        "option_type": None,
        "target_delta_min": None,
        "target_delta_max": None,
        "max_premium_per_trade": None,
        "max_contracts_per_trade": None,
        "iv_rank_min": None,
        "iv_rank_max": None,
        "roll_dte_threshold": None,
        "profit_take_pct": None,
        "max_loss_pct": None,
    }
    values.update(overrides)
    return AccountInsert(**values)


def _insert(conn, name: str, strategy: str = "Trend") -> None:
    AccountRepository(conn).insert(_make_account_insert(name=name, descriptive_name=name, strategy=strategy))


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
                strategy="Momentum",
                initial_cash=5000.0,
                created_at="2026-03-01T10:00:00",
                benchmark_ticker="QQQ",
                descriptive_name="Full Account",
                goal_min_return_pct=1.5,
                goal_max_return_pct=3.0,
                goal_period="weekly",
                learning_enabled=1,
                risk_policy="fixed_stop",
                stop_loss_pct=5.0,
                take_profit_pct=10.0,
                trade_size_pct=12.5,
                max_position_pct=25.0,
                instrument_mode="leaps",
                option_strike_offset_pct=2.0,
                option_min_dte=90,
                option_max_dte=180,
                option_type="call",
                target_delta_min=0.25,
                target_delta_max=0.45,
                max_premium_per_trade=300.0,
                max_contracts_per_trade=2,
                iv_rank_min=20.0,
                iv_rank_max=70.0,
                roll_dte_threshold=30,
                profit_take_pct=25.0,
                max_loss_pct=15.0,
            ),
        )
        row = AccountRepository(conn).fetch_by_name("full_acct")
        assert row is not None
        assert row["strategy"] == "Momentum"
        assert row["account_kind"] == "local"
        assert float(row["initial_cash"]) == pytest.approx(5000.0)
        assert row["benchmark_ticker"] == "QQQ"
        assert float(row["goal_min_return_pct"]) == pytest.approx(1.5)
        assert int(row["learning_enabled"]) == 1
        assert float(row["trade_size_pct"]) == pytest.approx(12.5)
        assert float(row["max_position_pct"]) == pytest.approx(25.0)
        assert row["instrument_mode"] == "leaps"
        assert int(row["option_min_dte"]) == 90


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
        _insert(conn, "z_acct", strategy="A_Strategy")
        _insert(conn, "a_acct", strategy="A_Strategy")
        _insert(conn, "m_acct", strategy="B_Strategy")
        rows = AccountRepository(conn).fetch_listing()
        names = [r["name"] for r in rows]
        assert names == ["a_acct", "z_acct", "m_acct"]

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
        repo.update(account_id=row["id"], updates=["strategy = ?"], params=["NewStrategy"])
        updated = repo.fetch_by_name("upd_acct")
        assert updated["strategy"] == "NewStrategy"

    def test_updates_multiple_fields(self, conn) -> None:
        _insert(conn, "multi_upd")
        repo = AccountRepository(conn)
        row = repo.fetch_by_name("multi_upd")
        repo.update(
            account_id=row["id"],
            updates=["risk_policy = ?", "stop_loss_pct = ?"],
            params=["fixed_stop", 7.5],
        )
        updated = repo.fetch_by_name("multi_upd")
        assert updated["risk_policy"] == "fixed_stop"
        assert float(updated["stop_loss_pct"]) == pytest.approx(7.5)


class TestFetchAllAccountNames:
    def test_returns_sorted_names(self, conn) -> None:
        _insert(conn, "zulu")
        _insert(conn, "alpha")
        _insert(conn, "mike")
        assert AccountRepository(conn).fetch_names() == ["alpha", "mike", "zulu"]

    def test_empty_table_returns_empty(self, conn) -> None:
        assert AccountRepository(conn).fetch_names() == []
