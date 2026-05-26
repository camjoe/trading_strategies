from __future__ import annotations

import pytest

from tests.trading.interfaces.cli.helpers import FakeConn


@pytest.fixture
def fake_conn() -> FakeConn:
    """A fresh ``FakeConn`` for CLI tests.

    Prefer this over constructing ``FakeConn()`` inline. Tests can check
    ``fake_conn.closed`` after ``main()`` to verify connection teardown.
    """
    return FakeConn()
