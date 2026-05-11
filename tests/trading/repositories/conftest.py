import pytest

from tests.support.repositories import insert_repository_account
from tests.support.sleeves import insert_test_sleeve


@pytest.fixture
def account_id(conn):
    return insert_repository_account(conn, name="sleeve_repo_acct")


@pytest.fixture
def sleeve_id(conn, account_id):
    return insert_test_sleeve(conn, account_id=account_id)
