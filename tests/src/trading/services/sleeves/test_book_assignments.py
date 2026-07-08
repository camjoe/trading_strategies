from __future__ import annotations

from trading.repositories.book_assignments import BookAssignmentRepository
from trading.repositories.book_bridge import book_id_for_sleeve, strategy_id_for_label
from trading.repositories.sleeves import SleeveRepository
from trading.services.sleeves.book_assignments import (
    assign_book_strategy,
    open_assignment_for_book,
)
from tests.support.repositories import insert_repository_account
from tests.support.sleeves import insert_test_sleeve

NOW = "2026-05-05T12:00:00Z"


def _insert_param_set(conn, param_set_id: int, strategy_name: str) -> None:
    conn.execute(
        """
        INSERT INTO strategy_param_sets (id, strategy_name, version, params_json, created_at, updated_at)
        VALUES (?, ?, 'v1', '{}', '2026-05-01T00:00:00Z', '2026-05-01T00:00:00Z')
        """,
        (param_set_id, strategy_name),
    )


def _sleeve_with_assignment(conn, *, name: str, strategy: str, param_set_id: int | None) -> int:
    account_id = insert_repository_account(conn, name=name)
    sleeve_id = insert_test_sleeve(conn, account_id=account_id)
    SleeveRepository(conn).insert_assignment(
        sleeve_id=sleeve_id,
        strategy_name=strategy,
        param_set_id=param_set_id,
        effective_from="2026-05-01T00:00:00Z",
        effective_to=None,
        is_incumbent=1,
        created_at="2026-05-01T00:00:00Z",
        updated_at="2026-05-01T00:00:00Z",
    )
    return sleeve_id


def test_open_assignment_lazy_bootstraps_from_sleeve(conn) -> None:
    _insert_param_set(conn, 101, "trend")
    sleeve_id = _sleeve_with_assignment(conn, name="acct_ba_boot", strategy="trend", param_set_id=101)
    book_id = book_id_for_sleeve(conn, sleeve_id, create=True)
    assert BookAssignmentRepository(conn).fetch_open(book_id=book_id) is None  # not yet bootstrapped

    view = open_assignment_for_book(conn, book_id=book_id, legacy_sleeve_id=sleeve_id)

    assert view is not None
    assert view.strategy_name == "trend"
    assert view.param_set_id == 101
    # The bootstrap persisted a real book assignment row.
    record = BookAssignmentRepository(conn).fetch_open(book_id=book_id)
    assert record is not None
    assert record.param_set_id == 101


def test_open_assignment_book_wins_over_stale_sleeve(conn) -> None:
    _insert_param_set(conn, 101, "trend")
    _insert_param_set(conn, 202, "meanrev")
    sleeve_id = _sleeve_with_assignment(conn, name="acct_ba_wins", strategy="trend", param_set_id=101)
    book_id = book_id_for_sleeve(conn, sleeve_id, create=True)
    # Book carries a *different* (newer) assignment than the sleeve row.
    strategy_id = strategy_id_for_label(conn, "meanrev", now_iso=NOW)
    assert strategy_id is not None
    BookAssignmentRepository(conn).assign_strategy(
        book_id=book_id,
        strategy_id=strategy_id,
        param_set_id=202,
        effective_from=NOW,
        created_at=NOW,
        updated_at=NOW,
    )

    view = open_assignment_for_book(conn, book_id=book_id, legacy_sleeve_id=sleeve_id)

    assert view is not None
    assert view.strategy_name == "meanrev"  # book record is authoritative
    assert view.param_set_id == 202


def test_open_assignment_none_when_neither_exists(conn) -> None:
    account_id = insert_repository_account(conn, name="acct_ba_none")
    sleeve_id = insert_test_sleeve(conn, account_id=account_id)  # no assignment anywhere
    book_id = book_id_for_sleeve(conn, sleeve_id, create=True)

    assert open_assignment_for_book(conn, book_id=book_id, legacy_sleeve_id=sleeve_id) is None
    assert open_assignment_for_book(conn, book_id=book_id) is None


def test_assign_book_strategy_writes_book_and_syncs_sleeve(conn) -> None:
    _insert_param_set(conn, 101, "trend")
    _insert_param_set(conn, 202, "meanrev")
    sleeve_id = _sleeve_with_assignment(conn, name="acct_ba_assign", strategy="trend", param_set_id=101)
    book_id = book_id_for_sleeve(conn, sleeve_id, create=True)

    view = assign_book_strategy(
        conn,
        book_id=book_id,
        strategy_name="meanrev",
        param_set_id=202,
        now_iso=NOW,
        legacy_sleeve_id=sleeve_id,
    )

    assert view.strategy_name == "meanrev"
    assert view.param_set_id == 202
    # Book record is the open assignment.
    record = BookAssignmentRepository(conn).fetch_open(book_id=book_id)
    assert record is not None
    assert record.param_set_id == 202
    # Legacy sleeve assignment stays in sync (dual-write until SR-3/SR-4 land).
    legacy = SleeveRepository(conn).fetch_active_assignment(sleeve_id=sleeve_id)
    assert legacy is not None
    assert legacy.strategy_name == "meanrev"
    assert legacy.param_set_id == 202
