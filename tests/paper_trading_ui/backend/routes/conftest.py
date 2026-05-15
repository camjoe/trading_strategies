from __future__ import annotations

from collections.abc import Callable

import pytest

from common.time import utc_now_iso
from trading.database.db_init import ensure_db
from trading.models import AccountConfig
from trading.services.accounts import create_account


@pytest.fixture
def seed_account() -> Callable[..., None]:
    def _seed(
        name: str,
        strategy: str = "trend_v1",
        initial_cash: float = 5000.0,
        benchmark: str = "SPY",
        **config_kwargs: object,
    ) -> None:
        conn = ensure_db()
        try:
            config = AccountConfig(**config_kwargs) if config_kwargs else None
            create_account(conn, name, strategy, initial_cash, benchmark, config=config)
        finally:
            conn.close()

    return _seed


@pytest.fixture
def seed_backtest_run() -> Callable[[str, str], None]:
    def _seed(account_name: str, run_name: str = "run-abc") -> None:
        conn = ensure_db()
        try:
            account = conn.execute("SELECT id FROM accounts WHERE name = ?", (account_name,)).fetchone()
            assert account is not None
            conn.execute(
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
                    "trading/config/trade_universe.txt",
                ),
            )
            conn.commit()
        finally:
            conn.close()

    return _seed
