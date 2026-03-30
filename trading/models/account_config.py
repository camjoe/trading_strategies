from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AccountConfig:
    """Configurable fields shared by create_account and configure_account."""

    descriptive_name: str | None = None
    goal_min_return_pct: float | None = None
    goal_max_return_pct: float | None = None
    goal_period: str | None = None
    learning_enabled: bool | None = None
    risk_policy: str | None = None
    stop_loss_pct: float | None = None
    take_profit_pct: float | None = None
    instrument_mode: str | None = None
    option_strike_offset_pct: float | None = None
    option_min_dte: int | None = None
    option_max_dte: int | None = None
    option_type: str | None = None
    target_delta_min: float | None = None
    target_delta_max: float | None = None
    max_premium_per_trade: float | None = None
    max_contracts_per_trade: int | None = None
    iv_rank_min: float | None = None
    iv_rank_max: float | None = None
    roll_dte_threshold: int | None = None
    profit_take_pct: float | None = None
    max_loss_pct: float | None = None
