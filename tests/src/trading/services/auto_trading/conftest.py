import pytest

from tests.support.sleeves import build_rotation_sleeve_env, build_sleeve_env


@pytest.fixture
def sleeve_env(conn):
    """Account + active sleeve + matching snapshot, function-scoped.

    Covers the common case where tests need a sleeve runtime environment
    without a rotation schedule.  Returns a SimpleNamespace with
    ``account_name``, ``account_id``, and ``sleeve_id``.
    """
    return build_sleeve_env(conn)


@pytest.fixture
def rotation_sleeve_env(conn):
    """Account with rotation schedule + sleeve + strategy assignment + metric rows + snapshot.

    Covers tests that exercise the rotation path.  Returns a SimpleNamespace
    with ``account_name``, ``account_id``, and ``sleeve_id``.
    """
    return build_rotation_sleeve_env(conn)
