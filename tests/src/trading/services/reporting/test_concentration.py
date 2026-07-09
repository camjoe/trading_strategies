"""Tests for trading.services.reporting.show_portfolio_concentration."""

from __future__ import annotations

import sqlite3

import pytest

from trading.repositories.book_bridge import default_book_id
from trading.repositories.positions import PositionRepository
from trading.services.analysis import concentration as concentration_module
from trading.services.reporting import show_portfolio_concentration


def test_no_positions_prints_placeholder(conn: sqlite3.Connection, capsys: pytest.CaptureFixture[str]) -> None:
    concentration = show_portfolio_concentration(conn)

    assert "No open positions found." in capsys.readouterr().out
    assert concentration.symbols == ()


def test_prints_symbol_sector_and_overlap_lines(
    conn: sqlite3.Connection,
    reporting_account: sqlite3.Row,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(concentration_module, "load_symbol_sector_map", lambda: {"AAPL": "tech"})
    PositionRepository(conn).upsert(
        book_id=default_book_id(conn, int(reporting_account["id"])),
        symbol="AAPL",
        qty=2.0,
        avg_cost=100.0,
        market_value=250.0,
        unrealized_pnl=50.0,
        updated_at="2026-07-09T00:00:00Z",
    )

    show_portfolio_concentration(conn)

    out = capsys.readouterr().out
    assert "Portfolio concentration by symbol (cross-account, D10):" in out
    assert "- AAPL | sector=tech | mv=250.00 | 100.00% | accounts=1 (acct_reporting)" in out
    assert "Sector rollup:" in out
    assert "- tech | mv=250.00 | 100.00% | symbols=1" in out
    assert "Total market value: 250.00" in out
    assert "Cross-account overlap: 0 symbol(s) held in more than one account" in out
