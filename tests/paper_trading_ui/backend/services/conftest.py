from __future__ import annotations

from collections.abc import Callable

import pytest

from trading.models import AccountConfig
from trading.services.accounts_service import create_account


@pytest.fixture
def create_test_account(conn) -> Callable[..., int]:
    """Factory fixture: creates an account in the test DB and returns its id."""

    def _factory(
        name: str,
        strategy: str = "trend",
        initial_cash: float = 1000.0,
        *,
        account_kind: str = "managed",
    ) -> int:
        create_account(conn, name, strategy, initial_cash, "SPY", config=AccountConfig(account_kind=account_kind))
        row = conn.execute("SELECT id FROM accounts WHERE name = ?", (name,)).fetchone()
        assert row is not None
        return int(row["id"])

    return _factory
