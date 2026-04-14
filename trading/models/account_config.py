from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields

from trading.utils.coercion import coerce_bool, coerce_float, coerce_int, coerce_str


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
    trade_size_pct: float | None = None
    max_position_pct: float | None = None
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

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> AccountConfig:
        return cls(
            descriptive_name=coerce_str(values.get("descriptive_name")),
            goal_min_return_pct=coerce_float(values.get("goal_min_return_pct")),
            goal_max_return_pct=coerce_float(values.get("goal_max_return_pct")),
            goal_period=coerce_str(values.get("goal_period")),
            learning_enabled=coerce_bool(values.get("learning_enabled")),
            risk_policy=coerce_str(values.get("risk_policy")),
            stop_loss_pct=coerce_float(values.get("stop_loss_pct")),
            take_profit_pct=coerce_float(values.get("take_profit_pct")),
            trade_size_pct=coerce_float(values.get("trade_size_pct")),
            max_position_pct=coerce_float(values.get("max_position_pct")),
            instrument_mode=coerce_str(values.get("instrument_mode")),
            option_strike_offset_pct=coerce_float(values.get("option_strike_offset_pct")),
            option_min_dte=coerce_int(values.get("option_min_dte")),
            option_max_dte=coerce_int(values.get("option_max_dte")),
            option_type=coerce_str(values.get("option_type")),
            target_delta_min=coerce_float(values.get("target_delta_min")),
            target_delta_max=coerce_float(values.get("target_delta_max")),
            max_premium_per_trade=coerce_float(values.get("max_premium_per_trade")),
            max_contracts_per_trade=coerce_int(values.get("max_contracts_per_trade")),
            iv_rank_min=coerce_float(values.get("iv_rank_min")),
            iv_rank_max=coerce_float(values.get("iv_rank_max")),
            roll_dte_threshold=coerce_int(values.get("roll_dte_threshold")),
            profit_take_pct=coerce_float(values.get("profit_take_pct")),
            max_loss_pct=coerce_float(values.get("max_loss_pct")),
        )

    @classmethod
    def has_any_field(cls, values: Mapping[str, object]) -> bool:
        return any(field_name in values for field_name in ACCOUNT_CONFIG_FIELD_NAMES)


ACCOUNT_CONFIG_FIELD_NAMES = tuple(field.name for field in fields(AccountConfig))
