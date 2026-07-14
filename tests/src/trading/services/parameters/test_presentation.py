"""Tests for trading.services.parameters.show_parameters."""

from __future__ import annotations

import sqlite3

import pytest

from tests.support.books import insert_test_book
from tests.support.repositories import insert_repository_account
from trading.services.parameters import show_parameters


def test_prints_groups_entries_and_fallback_notes(
    conn: sqlite3.Connection,
    capsys: pytest.CaptureFixture[str],
) -> None:
    account_id = insert_repository_account(conn, name="print_acct")
    insert_test_book(conn, account_id=account_id, name="book_a")

    view = show_parameters(conn, "print_acct")

    out = capsys.readouterr().out
    assert "Unified parameter source" in out
    assert "[global / trade throttle]" in out
    assert "max_trades_per_day = none (default)" in out
    assert "[account print_acct / book book_a / rotation]" in out
    assert "(no settings row - code defaults apply)" in out
    assert view.groups
