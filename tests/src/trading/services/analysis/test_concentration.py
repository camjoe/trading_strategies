"""Tests for trading.services.analysis.fetch_portfolio_concentration."""

from __future__ import annotations

import sqlite3

import pytest

from common.constants import SETTLEMENT_TICKER
from tests.support.analysis import make_analysis_account
from trading.models.portfolio import UNCATEGORIZED_SECTOR
from trading.repositories.book_bridge import default_book_id
from trading.repositories.positions import PositionRepository
from trading.services.analysis import concentration as concentration_module, fetch_portfolio_concentration


def upsert_position(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    symbol: str,
    market_value: float,
) -> None:
    PositionRepository(conn).upsert(
        book_id=default_book_id(conn, account_id),
        symbol=symbol,
        qty=1.0,
        avg_cost=market_value,
        market_value=market_value,
        unrealized_pnl=0.0,
        updated_at="2026-07-09T00:00:00Z",
    )


@pytest.fixture
def sector_map(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        concentration_module,
        "load_symbol_sector_map",
        lambda: {"AAPL": "tech", "MSFT": "tech"},
    )


class TestEmptyPortfolio:
    def test_no_positions(self, conn: sqlite3.Connection, sector_map: None) -> None:
        make_analysis_account(conn, "acct", initial_cash=1_000.0)

        concentration = fetch_portfolio_concentration(conn)

        assert concentration.symbols == ()
        assert concentration.sectors == ()
        assert concentration.total_market_value == 0.0


class TestSymbolConcentration:
    def test_aggregates_symbol_across_accounts(self, conn: sqlite3.Connection, sector_map: None) -> None:
        first = make_analysis_account(conn, "alpha", initial_cash=1_000.0)
        second = make_analysis_account(conn, "beta", initial_cash=1_000.0)
        upsert_position(conn, account_id=int(first["id"]), symbol="AAPL", market_value=600.0)
        upsert_position(conn, account_id=int(second["id"]), symbol="AAPL", market_value=200.0)
        upsert_position(conn, account_id=int(second["id"]), symbol="XLE", market_value=200.0)

        concentration = fetch_portfolio_concentration(conn)

        assert [entry.symbol for entry in concentration.symbols] == ["AAPL", "XLE"]
        aapl, xle = concentration.symbols
        assert aapl.market_value == pytest.approx(800.0)
        assert aapl.portfolio_pct == pytest.approx(80.0)
        assert aapl.account_count == 2
        assert aapl.account_names == ("alpha", "beta")
        assert aapl.sector == "tech"
        assert xle.portfolio_pct == pytest.approx(20.0)
        assert xle.account_count == 1
        assert xle.sector == UNCATEGORIZED_SECTOR
        assert concentration.total_market_value == pytest.approx(1_000.0)

    def test_settlement_ticker_excluded(self, conn: sqlite3.Connection, sector_map: None) -> None:
        account = make_analysis_account(conn, "acct", initial_cash=1_000.0)
        upsert_position(conn, account_id=int(account["id"]), symbol=SETTLEMENT_TICKER, market_value=500.0)
        upsert_position(conn, account_id=int(account["id"]), symbol="AAPL", market_value=500.0)

        concentration = fetch_portfolio_concentration(conn)

        assert [entry.symbol for entry in concentration.symbols] == ["AAPL"]
        assert concentration.total_market_value == pytest.approx(500.0)
        assert concentration.symbols[0].portfolio_pct == pytest.approx(100.0)


class TestSectorRollup:
    def test_sectors_aggregate_symbols(self, conn: sqlite3.Connection, sector_map: None) -> None:
        account = make_analysis_account(conn, "acct", initial_cash=1_000.0)
        account_id = int(account["id"])
        upsert_position(conn, account_id=account_id, symbol="AAPL", market_value=400.0)
        upsert_position(conn, account_id=account_id, symbol="MSFT", market_value=400.0)
        upsert_position(conn, account_id=account_id, symbol="XLE", market_value=200.0)

        concentration = fetch_portfolio_concentration(conn)

        assert [entry.sector for entry in concentration.sectors] == ["tech", UNCATEGORIZED_SECTOR]
        tech, uncategorized = concentration.sectors
        assert tech.market_value == pytest.approx(800.0)
        assert tech.portfolio_pct == pytest.approx(80.0)
        assert tech.symbol_count == 2
        assert uncategorized.market_value == pytest.approx(200.0)
        assert uncategorized.symbol_count == 1
