from __future__ import annotations

from tests.support.books import assign_test_book_strategy, insert_test_book
from tests.support.repositories import insert_repository_account
from trading.repositories.book_strategy_history import BookStrategyHistoryRepository
from trading.services.books.book_assignments import (
    active_strategy_for_account,
    assign_book_strategy,
    enumerate_trading_books,
    list_report_books,
    open_assignment_for_book,
    sync_default_book_assignment,
)

NOW = "2026-05-05T12:00:00Z"


def test_open_assignment_none_when_unassigned(conn) -> None:
    account_id = insert_repository_account(conn, name="acct_ba_none")
    book_id = insert_test_book(conn, account_id=account_id)

    assert open_assignment_for_book(conn, book_id=book_id) is None


def test_assign_book_strategy_roundtrips(conn) -> None:
    account_id = insert_repository_account(conn, name="acct_ba_assign")
    book_id = insert_test_book(conn, account_id=account_id)

    view = assign_book_strategy(conn, book_id=book_id, strategy_name="meanrev", now_iso=NOW)

    assert view.strategy_name == "meanrev"
    record = BookStrategyHistoryRepository(conn).fetch_open(book_id=book_id)
    assert record is not None
    assert record.strategy_id == view.strategy_id
    read_back = open_assignment_for_book(conn, book_id=book_id)
    assert read_back is not None
    assert read_back.strategy_name == "meanrev"


def test_enumerate_trading_books_lists_assigned_actives_only(conn) -> None:
    account_id = insert_repository_account(conn, name="acct_enum")
    assigned = insert_test_book(conn, account_id=account_id, name="core")
    assign_test_book_strategy(conn, book_id=assigned, strategy_name="trend")
    insert_test_book(conn, account_id=account_id, name="unassigned")
    paused = insert_test_book(conn, account_id=account_id, name="paused", status="paused")
    assign_test_book_strategy(conn, book_id=paused, strategy_name="trend")

    books = enumerate_trading_books(conn, account_id=account_id)

    assert [tb.book.id for tb in books] == [assigned]
    assert books[0].assignment.strategy_name == "trend"


def test_enumerate_trading_books_includes_assigned_default_book(conn) -> None:
    # The execution-mode collapse (ADR 014): the default book trades like any
    # other book once it carries an open assignment.
    from trading.repositories.book_bridge import default_book_id

    account_id = insert_repository_account(conn, name="acct_enum_default")
    default_id = default_book_id(conn, account_id)
    assign_book_strategy(conn, book_id=default_id, strategy_name="trend", now_iso=NOW)

    books = enumerate_trading_books(conn, account_id=account_id)

    assert [tb.book.id for tb in books] == [default_id]
    assert books[0].assignment.strategy_name == "trend"


def test_enumerate_trading_books_skips_unassigned_default_book(conn) -> None:
    from trading.repositories.book_bridge import default_book_id

    account_id = insert_repository_account(conn, name="acct_enum_default_bare")
    default_book_id(conn, account_id)

    assert enumerate_trading_books(conn, account_id=account_id) == []


def test_active_strategy_for_account_resolves_default_book_assignment(conn) -> None:
    account_id = insert_repository_account(conn, name="acct_active")

    # No default book yet: read-only, no bootstrap; unassigned label.
    assert active_strategy_for_account(conn, account_id) == "unassigned"
    assert conn.execute("SELECT COUNT(*) FROM books WHERE account_id = ?", (account_id,)).fetchone()[0] == 0

    sync_default_book_assignment(conn, account_id=account_id, strategy_name="meanrev", now_iso=NOW)

    assert active_strategy_for_account(conn, account_id) == "meanrev"


def test_sync_default_book_assignment_opens_and_is_idempotent(conn) -> None:
    account_id = insert_repository_account(conn, name="acct_sync")

    first = sync_default_book_assignment(conn, account_id=account_id, strategy_name="trend", now_iso=NOW)
    second = sync_default_book_assignment(conn, account_id=account_id, strategy_name="trend", now_iso=NOW)

    assert first.strategy_name == "trend"
    # Matching strategy is a no-op: same open assignment, no history churn.
    assert second == first
    open_rows = conn.execute(
        "SELECT COUNT(*) FROM book_strategy_history WHERE book_id = ?", (first.book_id,)
    ).fetchone()[0]
    assert open_rows == 1


def test_sync_default_book_assignment_rotates_on_strategy_change(conn) -> None:
    account_id = insert_repository_account(conn, name="acct_sync_change")

    first = sync_default_book_assignment(conn, account_id=account_id, strategy_name="trend", now_iso=NOW)
    changed = sync_default_book_assignment(conn, account_id=account_id, strategy_name="meanrev", now_iso=NOW)

    assert changed.strategy_name == "meanrev"
    assert changed.book_id == first.book_id
    closed = conn.execute(
        "SELECT COUNT(*) FROM book_strategy_history WHERE book_id = ? AND effective_to IS NOT NULL",
        (first.book_id,),
    ).fetchone()[0]
    assert closed == 1


def test_list_report_books_includes_paused_and_unassigned(conn) -> None:
    account_id = insert_repository_account(conn, name="acct_report")
    assigned = insert_test_book(conn, account_id=account_id, name="core")
    assign_test_book_strategy(conn, book_id=assigned, strategy_name="trend")
    unassigned = insert_test_book(conn, account_id=account_id, name="unassigned")
    paused = insert_test_book(conn, account_id=account_id, name="paused", status="paused")

    books = list_report_books(conn, account_id=account_id)

    by_id = {book.id: assignment for book, assignment in books}
    assert set(by_id) == {assigned, unassigned, paused}
    assert by_id[assigned] is not None
    assert by_id[unassigned] is None
