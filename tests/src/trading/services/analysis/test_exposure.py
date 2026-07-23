"""Tests for trading.services.analysis.fetch_portfolio_exposure."""

from __future__ import annotations

import sqlite3

import pytest

from tests.support.analysis import make_analysis_account
from trading.repositories.book_bridge import default_book_id
from trading.repositories.positions import PositionRepository
from trading.repositories.snapshots import EquitySnapshotRepository
from trading.services.analysis import fetch_portfolio_exposure


def insert_exposure_snapshot(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    snapshot_time: str,
    cash: float,
    market_value: float,
) -> None:
    EquitySnapshotRepository(conn).insert(
        account_id=account_id,
        snapshot_time=snapshot_time,
        cash=cash,
        market_value=market_value,
        equity=cash + market_value,
        realized_pnl=0.0,
        unrealized_pnl=0.0,
    )


def upsert_position(conn: sqlite3.Connection, *, account_id: int, symbol: str) -> None:
    PositionRepository(conn).upsert(
        book_id=default_book_id(conn, account_id),
        symbol=symbol,
        qty=1.0,
        avg_cost=100.0,
        market_value=100.0,
        unrealized_pnl=0.0,
        updated_at="2026-07-01T00:00:00Z",
    )


class TestEmptyPortfolio:
    def test_no_accounts(self, conn: sqlite3.Connection) -> None:
        rollup = fetch_portfolio_exposure(conn)
        assert rollup.accounts == ()
        assert rollup.accounts_with_snapshots == 0
        assert rollup.total_cash == 0.0
        assert rollup.total_market_value == 0.0
        assert rollup.total_equity == 0.0


class TestAccountExposures:
    def test_latest_snapshot_wins(self, conn: sqlite3.Connection) -> None:
        account = make_analysis_account(conn, "acct", initial_cash=1_000.0)
        account_id = int(account["id"])
        insert_exposure_snapshot(
            conn, account_id=account_id, snapshot_time="2026-07-01T00:00:00Z", cash=900.0, market_value=100.0
        )
        insert_exposure_snapshot(
            conn, account_id=account_id, snapshot_time="2026-07-02T00:00:00Z", cash=800.0, market_value=250.0
        )

        rollup = fetch_portfolio_exposure(conn)

        assert len(rollup.accounts) == 1
        exposure = rollup.accounts[0]
        assert exposure.account_name == "acct"
        assert exposure.snapshot_time == "2026-07-02T00:00:00Z"
        assert exposure.cash == pytest.approx(800.0)
        assert exposure.market_value == pytest.approx(250.0)
        assert exposure.equity == pytest.approx(1_050.0)

    def test_position_count_from_positions_table(self, conn: sqlite3.Connection) -> None:
        account = make_analysis_account(conn, "acct", initial_cash=1_000.0)
        account_id = int(account["id"])
        upsert_position(conn, account_id=account_id, symbol="AAPL")
        upsert_position(conn, account_id=account_id, symbol="MSFT")

        rollup = fetch_portfolio_exposure(conn)

        assert rollup.accounts[0].position_count == 2

    def test_account_without_snapshots_has_none_balances(self, conn: sqlite3.Connection) -> None:
        make_analysis_account(conn, "acct", initial_cash=1_000.0)

        rollup = fetch_portfolio_exposure(conn)

        exposure = rollup.accounts[0]
        assert exposure.snapshot_time is None
        assert exposure.cash is None
        assert exposure.market_value is None
        assert exposure.equity is None
        assert exposure.position_count == 0
        assert rollup.accounts_with_snapshots == 0


class TestTotals:
    def test_totals_sum_across_accounts(self, conn: sqlite3.Connection) -> None:
        first = make_analysis_account(conn, "alpha", initial_cash=1_000.0)
        second = make_analysis_account(conn, "beta", initial_cash=2_000.0)
        insert_exposure_snapshot(
            conn, account_id=int(first["id"]), snapshot_time="2026-07-02T00:00:00Z", cash=500.0, market_value=600.0
        )
        insert_exposure_snapshot(
            conn, account_id=int(second["id"]), snapshot_time="2026-07-02T00:00:00Z", cash=1_500.0, market_value=700.0
        )

        rollup = fetch_portfolio_exposure(conn)

        assert [e.account_name for e in rollup.accounts] == ["alpha", "beta"]
        assert rollup.accounts_with_snapshots == 2
        assert rollup.total_cash == pytest.approx(2_000.0)
        assert rollup.total_market_value == pytest.approx(1_300.0)
        assert rollup.total_equity == pytest.approx(3_300.0)

    def test_snapshotless_account_excluded_from_totals(self, conn: sqlite3.Connection) -> None:
        first = make_analysis_account(conn, "alpha", initial_cash=1_000.0)
        make_analysis_account(conn, "beta", initial_cash=2_000.0)
        insert_exposure_snapshot(
            conn, account_id=int(first["id"]), snapshot_time="2026-07-02T00:00:00Z", cash=400.0, market_value=100.0
        )

        rollup = fetch_portfolio_exposure(conn)

        assert len(rollup.accounts) == 2
        assert rollup.accounts_with_snapshots == 1
        assert rollup.total_cash == pytest.approx(400.0)
        assert rollup.total_market_value == pytest.approx(100.0)
        assert rollup.total_equity == pytest.approx(500.0)
