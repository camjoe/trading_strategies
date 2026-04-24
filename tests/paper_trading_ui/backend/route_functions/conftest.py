from __future__ import annotations

import sqlite3
from collections.abc import Callable

import pytest

from trading.models import AccountConfig
from trading.services.accounts import create_account


@pytest.fixture
def create_route_test_account() -> Callable[..., None]:
    def _create(
        conn: sqlite3.Connection,
        name: str,
        strategy: str = "trend_v1",
        initial_cash: float = 5000.0,
        benchmark: str = "SPY",
        **kwargs: object,
    ) -> None:
        create_account(conn, name, strategy, initial_cash, benchmark, config=AccountConfig(**kwargs) if kwargs else None)

    return _create
