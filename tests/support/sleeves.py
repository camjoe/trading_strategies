from __future__ import annotations

from trading.repositories.sleeves import insert_strategy_sleeve

DEFAULT_SLEEVE_TIMESTAMP = "2026-05-03T00:00:00Z"


def insert_test_sleeve(
    conn,
    *,
    account_id: int,
    name: str = "core",
    status: str = "active",
    base_ccy: str = "USD",
    start_equity: float = 10_000.0,
    current_cash: float | None = None,
    current_equity: float | None = None,
    created_at: str = DEFAULT_SLEEVE_TIMESTAMP,
    updated_at: str = DEFAULT_SLEEVE_TIMESTAMP,
) -> int:
    resolved_cash = start_equity if current_cash is None else current_cash
    resolved_equity = start_equity if current_equity is None else current_equity
    return insert_strategy_sleeve(
        conn,
        account_id=account_id,
        name=name,
        status=status,
        base_ccy=base_ccy,
        start_equity=start_equity,
        current_cash=resolved_cash,
        current_equity=resolved_equity,
        created_at=created_at,
        updated_at=updated_at,
    )


__all__ = [
    "insert_test_sleeve",
]
