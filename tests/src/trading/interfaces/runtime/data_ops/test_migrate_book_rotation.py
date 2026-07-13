"""Tests for the one-time book-rotation cutover data-op (ADR 014)."""

from __future__ import annotations

from tests.support.books import assign_test_book_strategy, insert_test_book
from tests.support.repositories import insert_repository_account
from trading.interfaces.runtime.data_ops.migrate_book_rotation import migrate_book_rotation
from trading.repositories.book_bridge import default_book_id
from trading.repositories.book_settings import BookRotationSettingsRepository
from trading.services.books.book_assignments import open_assignment_for_book
from trading.services.parameters import update_book_rotation_policy


def _set_account_rotation_columns(
    conn,
    account_id: int,
    *,
    enabled: int = 1,
    schedule: str | None = '["trend","meanrev"]',
    lookback_days: int | None = 45,
    active_strategy: str | None = None,
    active_index: int = 0,
) -> None:
    conn.execute(
        """
        UPDATE accounts
        SET rotation_enabled = ?, rotation_schedule = ?, rotation_lookback_days = ?,
            rotation_active_strategy = ?, rotation_active_index = ?
        WHERE id = ?
        """,
        (enabled, schedule, lookback_days, active_strategy, active_index, account_id),
    )
    conn.commit()


def test_syncs_scheduling_to_all_books_and_opens_default_assignment(conn) -> None:
    account_id = insert_repository_account(conn, name="cutover_acct", strategy="trend")
    book_book = insert_test_book(conn, account_id=account_id, name="book_book")
    assign_test_book_strategy(conn, book_id=book_book, strategy_name="meanrev")
    _set_account_rotation_columns(conn, account_id, active_strategy="meanrev")

    scheduling_synced, assignments_opened = migrate_book_rotation(conn)

    # Default book bootstrapped + both books synced.
    book_id = default_book_id(conn, account_id)
    assert scheduling_synced == 2
    repo = BookRotationSettingsRepository(conn)
    for synced_book in (book_id, book_book):
        row = repo.fetch(book_id=synced_book)
        assert row is not None
        assert row.rotation_enabled == 1
        assert row.rotation_schedule == '["trend","meanrev"]'
        assert row.rotation_lookback_days == 45

    # The default book got the legacy active strategy; the book book's
    # existing assignment was untouched.
    assert assignments_opened == 1
    default_assignment = open_assignment_for_book(conn, book_id=book_id)
    assert default_assignment is not None
    assert default_assignment.strategy_name == "meanrev"
    book_assignment = open_assignment_for_book(conn, book_id=book_book)
    assert book_assignment is not None
    assert book_assignment.strategy_name == "meanrev"


def test_idempotent_and_never_overwrites_open_assignment(conn) -> None:
    account_id = insert_repository_account(conn, name="cutover_idem", strategy="trend")
    _set_account_rotation_columns(conn, account_id)

    first = migrate_book_rotation(conn)
    second = migrate_book_rotation(conn)

    assert first == (1, 1)
    # Re-run re-syncs the same scheduling values but opens no new assignment.
    assert second == (1, 0)
    book_id = default_book_id(conn, account_id)
    open_rows = conn.execute(
        "SELECT COUNT(*) FROM book_strategy_assignments WHERE book_id = ? AND effective_to IS NULL",
        (book_id,),
    ).fetchone()[0]
    assert open_rows == 1


def test_preserves_policy_columns_when_resyncing_scheduling(conn) -> None:
    account_id = insert_repository_account(conn, name="cutover_policy", strategy="trend")
    _set_account_rotation_columns(conn, account_id)
    migrate_book_rotation(conn)
    update_book_rotation_policy(conn, account_name="cutover_policy", updates={"cooldown_days": 12})

    migrate_book_rotation(conn)

    row = BookRotationSettingsRepository(conn).fetch(book_id=default_book_id(conn, account_id))
    assert row is not None
    assert row.cooldown_days == 12
    assert row.rotation_enabled == 1


def test_unknown_active_strategy_gets_draft_row_and_assignment(conn) -> None:
    account_id = insert_repository_account(conn, name="cutover_draft", strategy="Custom Alpha")
    _set_account_rotation_columns(conn, account_id, schedule=None, lookback_days=None)

    _, assignments_opened = migrate_book_rotation(conn)

    assert assignments_opened == 1
    assignment = open_assignment_for_book(conn, book_id=default_book_id(conn, account_id))
    assert assignment is not None
    assert assignment.strategy_name == "custom alpha"
    draft = conn.execute("SELECT status FROM strategies WHERE strategy_key = 'custom alpha'").fetchone()
    assert draft is not None
