from __future__ import annotations


def insert_repository_account(
    conn,
    *,
    name: str = "repo_acct",
    initial_cash: float = 5000.0,
    benchmark_ticker: str = "SPY",
    created_at: str = "2026-01-01T00:00:00Z",
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO accounts (name, initial_cash, benchmark_ticker, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (name, initial_cash, benchmark_ticker, created_at, created_at),
    )
    conn.commit()
    assert cursor.lastrowid is not None
    return int(cursor.lastrowid)


__all__ = [
    "insert_repository_account",
]
