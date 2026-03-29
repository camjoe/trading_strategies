from __future__ import annotations

from trading.accounts import create_account


def create_test_account(conn, name: str, strategy: str = "trend", initial_cash: float = 1000.0) -> int:
    create_account(conn, name, strategy, initial_cash, "SPY")
    row = conn.execute("SELECT id FROM accounts WHERE name = ?", (name,)).fetchone()
    assert row is not None
    return int(row["id"])
