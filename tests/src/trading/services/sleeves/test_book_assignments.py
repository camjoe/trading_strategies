from __future__ import annotations

from trading.repositories.book_assignments import BookAssignmentRepository
from trading.services.sleeves.book_assignments import (
    assign_book_strategy,
    enumerate_trading_books,
    list_report_books,
    open_assignment_for_book,
)
from tests.support.repositories import insert_repository_account
from tests.support.sleeves import assign_test_book_strategy, insert_test_book

NOW = "2026-05-05T12:00:00Z"


def _insert_param_set(conn, param_set_id: int, strategy_name: str) -> None:
    conn.execute(
        """
        INSERT INTO strategy_param_sets (id, strategy_name, version, params_json, created_at, updated_at)
        VALUES (?, ?, 'v1', '{}', '2026-05-01T00:00:00Z', '2026-05-01T00:00:00Z')
        """,
        (param_set_id, strategy_name),
    )


def test_open_assignment_none_when_unassigned(conn) -> None:
    account_id = insert_repository_account(conn, name="acct_ba_none")
    book_id = insert_test_book(conn, account_id=account_id)

    assert open_assignment_for_book(conn, book_id=book_id) is None


def test_assign_book_strategy_roundtrips_with_param_set(conn) -> None:
    _insert_param_set(conn, 202, "meanrev")
    account_id = insert_repository_account(conn, name="acct_ba_assign")
    book_id = insert_test_book(conn, account_id=account_id)

    view = assign_book_strategy(conn, book_id=book_id, strategy_name="meanrev", param_set_id=202, now_iso=NOW)

    assert view.strategy_name == "meanrev"
    assert view.param_set_id == 202
    record = BookAssignmentRepository(conn).fetch_open(book_id=book_id)
    assert record is not None
    assert record.param_set_id == 202
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


def test_enumerate_trading_books_excludes_default_book(conn) -> None:
    from trading.repositories.book_bridge import default_book_id

    account_id = insert_repository_account(conn, name="acct_enum_default")
    default_id = default_book_id(conn, account_id)
    assign_book_strategy(conn, book_id=default_id, strategy_name="trend", param_set_id=None, now_iso=NOW)

    assert enumerate_trading_books(conn, account_id=account_id) == []


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
