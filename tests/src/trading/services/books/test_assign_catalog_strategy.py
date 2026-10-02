from __future__ import annotations

import pytest

from trading.domain.exceptions import NotFoundError, ValidationError
from trading.services.accounts.mutations import create_account, get_account
from trading.services.books.book_assignments import get_default_book, open_assignment_for_book
from trading.services.books.configuration import assign_catalog_strategy
from trading.services.strategy_catalog.mutations import configure_strategy, create_strategy_variant

_ACCOUNT = "assign_acct"


@pytest.fixture
def account(conn):
    create_account(conn, _ACCOUNT, "trend", 10_000.0, "SPY")
    create_strategy_variant(conn, strategy_key="trend_fast", primitive="trend", params={"fast_window": 5})
    return get_account(conn, _ACCOUNT)


def _strategy_count(conn) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM strategies").fetchone()[0])


def test_assigns_an_existing_strategy_and_reports_the_change(conn, account) -> None:
    previous, assigned = assign_catalog_strategy(
        conn, account_name=_ACCOUNT, book_name=None, strategy_key="TREND_FAST"
    )

    book = get_default_book(conn, account_id=account.id)
    assert (previous, assigned) == ("trend", "trend_fast")
    assert open_assignment_for_book(conn, book_id=book.id).strategy_name == "trend_fast"


def test_an_unknown_key_raises_and_mints_no_strategy(conn, account) -> None:
    before = _strategy_count(conn)

    with pytest.raises(NotFoundError, match="No strategy catalog row"):
        assign_catalog_strategy(conn, account_name=_ACCOUNT, book_name=None, strategy_key="trend_fsat")

    assert _strategy_count(conn) == before


def test_a_disabled_strategy_is_rejected(conn, account) -> None:
    configure_strategy(conn, strategy_key="trend_fast", enabled=False)
    with pytest.raises(ValidationError, match="disabled"):
        assign_catalog_strategy(conn, account_name=_ACCOUNT, book_name=None, strategy_key="trend_fast")


def test_reassigning_the_current_strategy_is_rejected(conn, account) -> None:
    with pytest.raises(ValidationError, match="already runs"):
        assign_catalog_strategy(conn, account_name=_ACCOUNT, book_name=None, strategy_key="trend")


def test_an_unknown_book_is_rejected(conn, account) -> None:
    with pytest.raises(NotFoundError, match="Book not found"):
        assign_catalog_strategy(conn, account_name=_ACCOUNT, book_name="no_such_book", strategy_key="trend_fast")
