"""Tests for trading.services.parameters.update_book_rotation_policy (P7)."""

from __future__ import annotations

import sqlite3

import pytest

from tests.support.books import insert_test_book
from tests.support.repositories import insert_repository_account
from trading.domain.exceptions import NotFoundError
from trading.repositories.book_bridge import default_book_id
from trading.repositories.book_settings import BookRotationSettingsRepository
from trading.services.parameters import update_book_rotation_policy


@pytest.fixture
def account_with_book(conn: sqlite3.Connection) -> tuple[str, int]:
    account_id = insert_repository_account(conn, name="policy_acct")
    book_id = insert_test_book(conn, account_id=account_id, name="book_a")
    return "policy_acct", book_id


def test_creates_policy_row_for_named_book(conn: sqlite3.Connection, account_with_book: tuple[str, int]) -> None:
    account_name, book_id = account_with_book

    saved = update_book_rotation_policy(
        conn,
        account_name=account_name,
        book_name="book_a",
        updates={"cooldown_days": 14, "stability_weight": 0.5},
    )

    assert saved.book_id == book_id
    assert saved.cooldown_days == 14
    assert saved.stability_weight == 0.5
    assert saved.min_trades_in_window is None


def test_second_update_merges_and_none_clears(conn: sqlite3.Connection, account_with_book: tuple[str, int]) -> None:
    account_name, _ = account_with_book
    update_book_rotation_policy(
        conn,
        account_name=account_name,
        book_name="book_a",
        updates={"cooldown_days": 14, "stability_weight": 0.5},
    )

    saved = update_book_rotation_policy(
        conn,
        account_name=account_name,
        book_name="book_a",
        updates={"stability_weight": None, "regime_fit_weight": 0.2},
    )

    assert saved.cooldown_days == 14
    assert saved.stability_weight is None
    assert saved.regime_fit_weight == 0.2


def test_policy_write_preserves_scheduling_fields(
    conn: sqlite3.Connection, account_with_book: tuple[str, int]
) -> None:
    account_name, book_id = account_with_book
    BookRotationSettingsRepository(conn).upsert_rotation_scheduling(
        book_id=book_id,
        rotation_enabled=1,
        rotation_lookback_days=45,
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )

    update_book_rotation_policy(
        conn,
        account_name=account_name,
        book_name="book_a",
        updates={"cooldown_days": 5},
    )

    saved = BookRotationSettingsRepository(conn).fetch(book_id=book_id)
    assert saved is not None
    assert saved.rotation_enabled == 1
    assert saved.rotation_lookback_days == 45
    assert saved.cooldown_days == 5


def test_default_book_resolution_bootstraps(conn: sqlite3.Connection) -> None:
    insert_repository_account(conn, name="fresh_acct")

    saved = update_book_rotation_policy(
        conn,
        account_name="fresh_acct",
        updates={"cooldown_days": 3},
    )

    account_id = int(conn.execute("SELECT id FROM accounts WHERE name = 'fresh_acct'").fetchone()["id"])
    assert saved.book_id == default_book_id(conn, account_id)
    assert saved.cooldown_days == 3


def test_unknown_field_rejected(conn: sqlite3.Connection, account_with_book: tuple[str, int]) -> None:
    account_name, _ = account_with_book
    with pytest.raises(ValueError, match="Unknown rotation policy fields"):
        update_book_rotation_policy(
            conn,
            account_name=account_name,
            book_name="book_a",
            updates={"rolling_window_days": 10},
        )


def test_empty_updates_rejected(conn: sqlite3.Connection, account_with_book: tuple[str, int]) -> None:
    account_name, _ = account_with_book
    with pytest.raises(ValueError, match="No rotation policy fields"):
        update_book_rotation_policy(conn, account_name=account_name, book_name="book_a", updates={})


def test_unknown_account_and_book_raise(conn: sqlite3.Connection, account_with_book: tuple[str, int]) -> None:
    account_name, _ = account_with_book
    with pytest.raises(NotFoundError):
        update_book_rotation_policy(conn, account_name="missing", updates={"cooldown_days": 1})
    with pytest.raises(NotFoundError):
        update_book_rotation_policy(
            conn, account_name=account_name, book_name="missing_book", updates={"cooldown_days": 1}
        )
