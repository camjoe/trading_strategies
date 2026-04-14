from __future__ import annotations

from collections.abc import Callable, Mapping
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
        kwargs = {
            field_name: coercer(values[field_name])
            for field_name, coercer in ACCOUNT_CONFIG_FIELD_COERCERS.items()
            if field_name in values
        }
        return cls(**kwargs)

    @classmethod
    def has_any_field(cls, values: Mapping[str, object]) -> bool:
        return any(field_name in values for field_name in ACCOUNT_CONFIG_FIELD_NAMES)


ACCOUNT_CONFIG_FIELD_NAMES = tuple(field.name for field in fields(AccountConfig))

ACCOUNT_CONFIG_FIELD_COERCERS: dict[str, Callable[[object], object | None]] = {
    "descriptive_name": coerce_str,
    "goal_min_return_pct": coerce_float,
    "goal_max_return_pct": coerce_float,
    "goal_period": coerce_str,
    "learning_enabled": coerce_bool,
    "risk_policy": coerce_str,
    "stop_loss_pct": coerce_float,
    "take_profit_pct": coerce_float,
    "trade_size_pct": coerce_float,
    "max_position_pct": coerce_float,
    "instrument_mode": coerce_str,
    "option_strike_offset_pct": coerce_float,
    "option_min_dte": coerce_int,
    "option_max_dte": coerce_int,
    "option_type": coerce_str,
    "target_delta_min": coerce_float,
    "target_delta_max": coerce_float,
    "max_premium_per_trade": coerce_float,
    "max_contracts_per_trade": coerce_int,
    "iv_rank_min": coerce_float,
    "iv_rank_max": coerce_float,
    "roll_dte_threshold": coerce_int,
    "profit_take_pct": coerce_float,
    "max_loss_pct": coerce_float,
}
