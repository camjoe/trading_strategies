from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AccountInsert:
    """Repository-ready create payload after validation, defaults, and normalization."""

    name: str
    account_kind: str
    strategy: str
    initial_cash: float
    created_at: str
    benchmark_ticker: str
    descriptive_name: str
    goal_min_return_pct: float | None
    goal_max_return_pct: float | None
    goal_period: str
    learning_enabled: int
    risk_policy: str
    stop_loss_pct: float | None
    take_profit_pct: float | None
    trade_size_pct: float | None
    max_position_pct: float | None
    instrument_mode: str
    option_strike_offset_pct: float | None
    option_min_dte: int | None
    option_max_dte: int | None
    option_type: str | None
    target_delta_min: float | None
    target_delta_max: float | None
    max_premium_per_trade: float | None
    max_contracts_per_trade: int | None
    iv_rank_min: float | None
    iv_rank_max: float | None
    roll_dte_threshold: int | None
    profit_take_pct: float | None
    max_loss_pct: float | None
    trade_universes: str | None = None
