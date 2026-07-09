import pytest

from tests.support.sleeves import build_book_env, build_rotation_book_env


@pytest.fixture
def book_env(conn):
    """Account + active book + matching snapshot, function-scoped."""
    return build_book_env(conn)


@pytest.fixture
def rotation_book_env(conn):
    """Account with rotation schedule + book + assignment + metrics + snapshot."""
    return build_rotation_book_env(conn)
