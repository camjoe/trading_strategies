import pytest

from tests.support.books import insert_test_book
from tests.support.repositories import insert_repository_account


@pytest.fixture
def account_id(conn):
    return insert_repository_account(conn, name="book_repo_acct")


@pytest.fixture
def book_id(conn, account_id):
    return insert_test_book(conn, account_id=account_id)
