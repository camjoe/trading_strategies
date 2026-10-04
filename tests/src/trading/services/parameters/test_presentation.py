"""Tests for trading.services.parameters.show_parameters."""

from __future__ import annotations

import sqlite3

import pytest

from tests.support.books import insert_test_book
from tests.support.repositories import insert_repository_account
from trading.repositories.book_rotation_settings import BookRotationSettingsRepository
from trading.services.parameters.presentation import show_book_rotation_history, show_parameters


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


def test_show_book_rotation_history_prints_no_changes_message(
    conn: sqlite3.Connection,
    capsys: pytest.CaptureFixture[str],
) -> None:
    account_id = insert_repository_account(conn, name="history_acct")
    insert_test_book(conn, account_id=account_id, name="book_a")

    events = show_book_rotation_history(conn, account_name="history_acct", book_name="book_a")

    assert events == []
    assert "No rotation settings changes recorded for account history_acct." in capsys.readouterr().out


def test_show_book_rotation_history_prints_recorded_changes(
    conn: sqlite3.Connection,
    capsys: pytest.CaptureFixture[str],
) -> None:
    account_id = insert_repository_account(conn, name="history_acct2")
    book_id = insert_test_book(conn, account_id=account_id, name="book_a")
    BookRotationSettingsRepository(conn).upsert_rotation_scheduling(
        book_id=book_id,
        rotation_enabled=1,
        rotation_lookback_days=30,
        rotation_schedule=None,
        created_at="2026-07-26T00:00:00Z",
        updated_at="2026-07-26T00:00:00Z",
    )

    events = show_book_rotation_history(conn, account_name="history_acct2", book_name="book_a")

    out = capsys.readouterr().out
    assert len(events) == 1
    assert "Rotation settings change history" in out
    assert "scheduling" in out
    assert "rotation_enabled: None -> 1" in out
