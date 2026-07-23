import sqlite3

import pytest

import trading.services.accounts.mutations as account_mutations
from trading.models.accounts.account_config import AccountConfig
from trading.repositories.book_bridge import default_book_id
from trading.services.accounts import create_account, get_account, set_account_strategy
from trading.services.accounts.queries import find_account as get_account_or_none
from trading.services.books.book_assignments import open_assignment_for_book


def test_create_account_rejects_unknown_strategy_name() -> None:
    with pytest.raises(ValueError, match="Unknown strategy 'mystery_strategy'"):
        create_account(
            sqlite3.connect(":memory:"),
            "acct",
            "mystery_strategy",
            5000.0,
            "SPY",
            config=AccountConfig(),
        )


def test_create_account_opens_default_book_assignment(conn) -> None:
    create_account(conn, "acct_new", "Trend", 5000.0, "SPY")

    account = get_account(conn, "acct_new")
    assignment = open_assignment_for_book(conn, book_id=default_book_id(conn, account.id))
    assert assignment is not None
    assert assignment.strategy_name == "trend"


def test_create_account_rolls_back_when_book_configuration_fails(conn, monkeypatch) -> None:
    def fail_book_configuration(*args, **kwargs) -> None:
        raise RuntimeError("book configuration failed")

    monkeypatch.setattr(account_mutations, "_apply_book_settings_to_default_book", fail_book_configuration)

    with pytest.raises(RuntimeError, match="book configuration failed"):
        create_account(conn, "acct_create_rollback", "Trend", 5000.0, "SPY")

    assert get_account_or_none(conn, "acct_create_rollback") is None


def test_set_account_strategy_syncs_default_book_assignment(conn) -> None:
    create_account(conn, "acct_edit", "Trend", 5000.0, "SPY")

    set_account_strategy(conn, "acct_edit", "MeanRev")

    account = get_account(conn, "acct_edit")
    assignment = open_assignment_for_book(conn, book_id=default_book_id(conn, account.id))
    assert assignment is not None
    assert assignment.strategy_name == "meanrev"
