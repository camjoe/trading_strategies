"""Tests for trading.services.reporting.show_portfolio_exposure."""

from __future__ import annotations

import sqlite3

import pytest

from tests.support.books import ensure_default_book_id
from trading.repositories.snapshots import EquitySnapshotRepository
from trading.services.reporting import show_portfolio_exposure


def test_no_accounts_prints_placeholder(conn: sqlite3.Connection, capsys: pytest.CaptureFixture[str]) -> None:
    rollup = show_portfolio_exposure(conn)

    assert "No accounts found." in capsys.readouterr().out
    assert rollup.accounts == ()


def test_prints_account_lines_and_totals(
    conn: sqlite3.Connection,
    reporting_account: sqlite3.Row,
    capsys: pytest.CaptureFixture[str],
) -> None:
    EquitySnapshotRepository(conn).insert_for_book(
        book_id=ensure_default_book_id(conn, int(reporting_account["id"])),
        snapshot_time="2026-07-02T00:00:00Z",
        cash=750.0,
        market_value=250.0,
        equity=1_000.0,
        realized_pnl=0.0,
        unrealized_pnl=0.0,
    )

    rollup = show_portfolio_exposure(conn)

    out = capsys.readouterr().out
    assert "Portfolio exposure rollup (latest snapshot per account):" in out
    assert "- acct_reporting | as_of=2026-07-02T00:00:00Z | equity=1000.00 cash=750.00 mv=250.00 positions=0" in out
    assert "Totals (1 of 1 accounts with snapshots): equity=1000.00 cash=750.00 mv=250.00" in out
    assert rollup.total_equity == pytest.approx(1_000.0)


def test_snapshotless_account_line(
    conn: sqlite3.Connection,
    reporting_account: sqlite3.Row,
    capsys: pytest.CaptureFixture[str],
) -> None:
    show_portfolio_exposure(conn)

    out = capsys.readouterr().out
    assert "- acct_reporting | no snapshots yet | positions=0" in out
    assert "Totals (0 of 1 accounts with snapshots): equity=0.00 cash=0.00 mv=0.00" in out
