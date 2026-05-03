from __future__ import annotations

from tests.support.account_records import make_account_record


def make_accounts_service_row(
    *,
    id: int = 1,
    name: str = "acct",
    descriptive_name: str = "Account",
    strategy: str = "Trend",
    initial_cash: float = 5000.0,
    benchmark_ticker: str = "SPY",
    goal_min_return_pct: float | None = None,
    goal_max_return_pct: float | None = None,
    goal_period: str = "monthly",
    learning_enabled: int = 0,
    risk_policy: str = "none",
    trade_size_pct: float = 10.0,
    max_position_pct: float = 20.0,
    instrument_mode: str = "equity",
    created_at: str = "2026-01-01T00:00:00",
    rotation_enabled: int = 0,
    rotation_active_strategy: str | None = None,
):
    return make_account_record(
        id=id,
        name=name,
        descriptive_name=descriptive_name,
        strategy=strategy,
        initial_cash=initial_cash,
        created_at=created_at,
        benchmark_ticker=benchmark_ticker,
        goal_min_return_pct=goal_min_return_pct,
        goal_max_return_pct=goal_max_return_pct,
        goal_period=goal_period,
        learning_enabled=learning_enabled,
        risk_policy=risk_policy,
        trade_size_pct=trade_size_pct,
        max_position_pct=max_position_pct,
        instrument_mode=instrument_mode,
        rotation_enabled=rotation_enabled,
        rotation_active_strategy=rotation_active_strategy,
    )


__all__ = [
    "make_accounts_service_row",
]
