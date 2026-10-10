from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient

from common.time import utc_now_iso
from infrastructure.database.connection import ensure_db
from trading.models import AccountConfig
from trading.services.accounts.mutations import create_account


@pytest.fixture
def api_conn(api_client: TestClient) -> Iterator[sqlite3.Connection]:  # noqa: ARG001
    """Managed connection to the backend DB configured by ``api_client``.

    Declaring ``api_client`` as a parameter guarantees the backend is set up
    before ``ensure_db()`` is called, then closes the connection on teardown.
    Tests and seed fixtures that need direct DB access should use this instead
    of calling ``ensure_db()`` manually.
    """
    conn = ensure_db()
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def seed_account(api_conn: sqlite3.Connection) -> Callable[..., None]:
    def _seed(
        name: str,
        strategy: str = "trend_v1",
        initial_cash: float = 5000.0,
        benchmark: str = "SPY",
        **config_kwargs: object,
    ) -> None:
        config = AccountConfig(**config_kwargs) if config_kwargs else None
        create_account(api_conn, name, strategy, initial_cash, benchmark, config=config)

    return _seed


@pytest.fixture
def seed_backtest_run(api_conn: sqlite3.Connection) -> Callable[[str, str], None]:
    def _seed(account_name: str, run_name: str = "run-abc") -> None:
        account = api_conn.execute("SELECT id FROM accounts WHERE name = ?", (account_name,)).fetchone()
        assert account is not None
        api_conn.execute(
            """
            INSERT INTO backtest_runs (
                account_id, run_name, start_date, end_date, created_at,
                slippage_bps, fee_per_trade, tickers_file
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(account["id"]),
                run_name,
                "2026-01-01",
                "2026-01-31",
                utc_now_iso(),
                5.0,
                0.0,
                "src/infrastructure/config/trade_universes/default.txt",
            ),
        )
        api_conn.commit()

    return _seed
