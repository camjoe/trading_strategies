from __future__ import annotations

import pytest

from trading.repositories.accounts_repository import (
    fetch_account_by_name,
    fetch_account_listing_rows,
    fetch_account_rows_excluding_name,
    fetch_all_account_names_from_conn,
    insert_account,
    update_account_benchmark,
    update_account_fields,
)


def _insert(conn, name: str, strategy: str = "Trend") -> None:
    insert_account(
        conn,
        name=name,
        strategy=strategy,
        initial_cash=1000.0,
        created_at="2026-01-01T00:00:00",
        benchmark_ticker="SPY",
        descriptive_name=name,
        goal_min_return_pct=None,
        goal_max_return_pct=None,
        goal_period="monthly",
        learning_enabled=0,
        risk_policy="none",
        stop_loss_pct=None,
        take_profit_pct=None,
        trade_size_pct=10.0,
        max_position_pct=20.0,
        instrument_mode="equity",
        option_strike_offset_pct=None,
        option_min_dte=None,
        option_max_dte=None,
        option_type=None,
        target_delta_min=None,
        target_delta_max=None,
        max_premium_per_trade=None,
        max_contracts_per_trade=None,
        iv_rank_min=None,
        iv_rank_max=None,
        roll_dte_threshold=None,
        profit_take_pct=None,
        max_loss_pct=None,
    )


class TestFetchAccountByName:
    def test_returns_row_for_existing_account(self, conn) -> None:
        _insert(conn, "acct_a")
        row = fetch_account_by_name(conn, "acct_a")
        assert row is not None
        assert row["name"] == "acct_a"

    def test_returns_none_for_missing_account(self, conn) -> None:
        assert fetch_account_by_name(conn, "ghost") is None


class TestInsertAccount:
    def test_round_trip_stores_all_fields(self, conn) -> None:
        insert_account(
            conn,
            name="full_acct",
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
        )
        row = fetch_account_by_name(conn, "full_acct")
        assert row is not None
        assert row["strategy"] == "Momentum"
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
        row = fetch_account_by_name(conn, "bench_acct")
        update_account_benchmark(conn, account_id=row["id"], benchmark_ticker="QQQ")
        updated = fetch_account_by_name(conn, "bench_acct")
        assert updated["benchmark_ticker"] == "QQQ"


class TestFetchAccountListingRows:
    def test_returns_all_accounts_ordered_by_strategy_then_name(self, conn) -> None:
        _insert(conn, "z_acct", strategy="A_Strategy")
        _insert(conn, "a_acct", strategy="A_Strategy")
        _insert(conn, "m_acct", strategy="B_Strategy")
        rows = fetch_account_listing_rows(conn)
        names = [r["name"] for r in rows]
        assert names == ["a_acct", "z_acct", "m_acct"]

    def test_empty_table_returns_empty_list(self, conn) -> None:
        assert fetch_account_listing_rows(conn) == []


class TestFetchAccountRowsExcludingName:
    def test_excludes_named_account(self, conn) -> None:
        _insert(conn, "keep_me")
        _insert(conn, "exclude_me")
        rows = fetch_account_rows_excluding_name(conn, excluded_name="exclude_me")
        names = [r["name"] for r in rows]
        assert "exclude_me" not in names
        assert "keep_me" in names

    def test_ordered_by_name(self, conn) -> None:
        _insert(conn, "bravo")
        _insert(conn, "alpha")
        _insert(conn, "skip_me")
        rows = fetch_account_rows_excluding_name(conn, excluded_name="skip_me")
        names = [r["name"] for r in rows]
        assert names == ["alpha", "bravo"]


class TestUpdateAccountFields:
    def test_updates_single_field(self, conn) -> None:
        _insert(conn, "upd_acct")
        row = fetch_account_by_name(conn, "upd_acct")
        update_account_fields(
            conn,
            account_id=row["id"],
            updates=["strategy = ?"],
            params=["NewStrategy"],
        )
        updated = fetch_account_by_name(conn, "upd_acct")
        assert updated["strategy"] == "NewStrategy"

    def test_updates_multiple_fields(self, conn) -> None:
        _insert(conn, "multi_upd")
        row = fetch_account_by_name(conn, "multi_upd")
        update_account_fields(
            conn,
            account_id=row["id"],
            updates=["risk_policy = ?", "stop_loss_pct = ?"],
            params=["fixed_stop", 7.5],
        )
        updated = fetch_account_by_name(conn, "multi_upd")
        assert updated["risk_policy"] == "fixed_stop"
        assert float(updated["stop_loss_pct"]) == pytest.approx(7.5)


class TestFetchAllAccountNamesFromConn:
    def test_returns_sorted_names(self, conn) -> None:
        _insert(conn, "zulu")
        _insert(conn, "alpha")
        _insert(conn, "mike")
        assert fetch_all_account_names_from_conn(conn) == ["alpha", "mike", "zulu"]

    def test_empty_table_returns_empty(self, conn) -> None:
        assert fetch_all_account_names_from_conn(conn) == []
